"""
MIND Recorder — Asistente de escritorio (Windows / macOS / Linux)
===============================================================
Captura loopback (audio del sistema) + micrófono, los mezcla a mono y
sube los chunks WAV a la API de MIND. Todo con Tkinter (viene con Python)
y sounddevice (PortAudio). Sin dependencias comerciales.

Empaquetado como .exe: pyinstaller --onefile --windowed mind_desktop.py
"""
from __future__ import annotations

import io
import json
import os
import platform
import struct
import threading
import time
import wave
from configparser import ConfigParser
from pathlib import Path
from queue import Queue
from tkinter import ttk
from tkinter import filedialog, messagebox
import tkinter as tk

import requests
import sounddevice as sd

__version__ = "1.0.0"
APP_NAME = "MIND Recorder"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / ".config")) / APP_NAME

# Parámetros de audio (mismos que el frontend web)
RATE = 16000
CHUNK_SEC = 5
SILENCE_RMS = 0.01


# ── Utilidades de audio ─────────────────────────────────────────────────────

def rms(samples: list[float]) -> float:
    if not samples:
        return 0
    s = sum(x * x for x in samples)
    return (s / len(samples)) ** 0.5


def make_wav(samples: list[float]) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32768, min(32767, int(s * 32767))))
            for s in samples
        ))
    return buf.getvalue()


def find_loopback_device() -> int | None:
    """Busca automáticamente un dispositivo de loopback/monitor."""
    for i, dev in enumerate(sd.query_devices()):
        name = (dev["name"] or "").lower()
        if any(k in name for k in ("loopback", "monitor", "mme", "wasapi", "pulse")):
            # Primer dispositivo con salida (outputs > 0) y que suene a loopback
            if dev["max_output_channels"] > 0 or "loopback" in name:
                if dev["max_input_channels"] > 0:
                    return i
    return None


# ── Configuración persistente ────────────────────────────────────────────────

class Config:
    def __init__(self):
        self.server_url = "https://mind.versat.com"
        self.username = ""
        self.password = ""
        self.tenant_id = ""
        self.language = "es"
        self.input_device = ""          # nombre del dispositivo loopback
        self.mic_device = ""            # nombre del dispositivo mic
        self.load()

    @property
    def config_path(self) -> Path:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return CONFIG_DIR / "config.json"

    def load(self):
        path = self.config_path
        if not path.exists():
            return
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            self.server_url = d.get("server_url", self.server_url)
            self.username = d.get("username", "")
            self.password = d.get("password", "")
            self.tenant_id = str(d.get("tenant_id", ""))
            self.language = d.get("language", "es")
            self.input_device = d.get("input_device", "")
            self.mic_device = d.get("mic_device", "")
        except (json.JSONDecodeError, OSError):
            pass

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps({
            "server_url": self.server_url,
            "username": self.username,
            "password": self.password,
            "tenant_id": self.tenant_id,
            "language": self.language,
            "input_device": self.input_device,
            "mic_device": self.mic_device,
        }, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Cliente API (sesión con cookies) ─────────────────────────────────────────

class MindAPI:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = requests.Session()

    @property
    def base(self) -> str:
        return self.cfg.server_url.rstrip("/") + "/api/admin"

    def login(self) -> bool:
        """Autentica y guarda la cookie en la sesión."""
        try:
            resp = self.session.post(
                f"{self.base}/login",
                json={
                    "username": self.cfg.username,
                    "password": self.cfg.password,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return True
            # Mensaje de error más claro
            detail = resp.json().get("detail") if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:200]
            raise ConnectionError(detail or f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            raise ConnectionError(str(e)) from e

    def create_meeting(self, title: str) -> dict:
        params = {}
        if self.cfg.tenant_id:
            params["tenant_id"] = self.cfg.tenant_id
        resp = self.session.post(
            f"{self.base}/meetings",
            json={
                "title": title,
                "language": self.cfg.language,
                "stt_provider": "deepgram",
                "diarize": True,
            },
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def upload_chunk(self, meeting_id: int, seq: int, wav: bytes, silent: bool):
        params = {"tenant_id": self.cfg.tenant_id} if self.cfg.tenant_id else {}
        resp = self.session.post(
            f"{self.base}/meetings/{meeting_id}/chunks",
            params=params,
            files={"audio": (f"c-{seq}.wav", wav, "audio/wav")},
            data={"seq": seq, "duration_ms": CHUNK_SEC * 1000, "silent": "1" if silent else "0"},
            timeout=30,
        )
        resp.raise_for_status()

    def finish_meeting(self, meeting_id: int) -> dict:
        params = {"tenant_id": self.cfg.tenant_id} if self.cfg.tenant_id else {}
        resp = self.session.post(
            f"{self.base}/meetings/{meeting_id}/finish",
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_transcript(self, meeting_id: int) -> str:
        params = {"tenant_id": self.cfg.tenant_id} if self.cfg.tenant_id else {}
        resp = self.session.get(
            f"{self.base}/meetings/{meeting_id}/transcript",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("transcript", "")


# ── Ventana principal ────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{__version__}")
        self.resizable(False, False)
        self.configure(bg="#0d0d0d")  # Mismo estilo oscuro de MIND
        self.option_add("*Font", ("Consolas", 11))

        self.cfg = Config()
        self.api = MindAPI(self.cfg)

        # Estado de grabación
        self._recording = False
        self._meeting_id: int | None = None
        self._buffer: list[float] = []
        self._seq = 0
        self._stream: sd.InputStream | None = None
        self._thread: threading.Thread | None = None
        self._start_time: float = 0
        self._live_transcript = ""
        self._device_id: int | None = None
        self._mic_dev_id: int | None = None

        self._build_ui()
        self._load_device_best_guess()

    def _load_device_best_guess(self):
        """Intenta resolver el dispositivo guardado o auto-detecta."""
        if self.cfg.input_device:
            for i, dev in enumerate(sd.query_devices()):
                if dev["name"] == self.cfg.input_device and dev["max_input_channels"] > 0:
                    self._device_id = i
                    break
        if self._device_id is None:
            self._device_id = find_loopback_device() or sd.default.device[0]

        if self.cfg.mic_device:
            for i, dev in enumerate(sd.query_devices()):
                if dev["name"] == self.cfg.mic_device and dev["max_input_channels"] > 0:
                    self._mic_dev_id = i
                    break
        if self._mic_dev_id is None:
            self._mic_dev_id = sd.default.device[0]

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=16)

        # Pestaña Configuración
        self.tab_cfg = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_cfg, text="Configuración")
        self._build_config_tab()

        # Pestaña Grabación
        self.tab_rec = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_rec, text="Grabación")
        self._build_rec_tab()

    def _build_config_tab(self):
        f = ttk.Frame(self.tab_cfg, padding=12)
        f.pack(fill="both", expand=True)

        row = 0
        ttk.Label(f, text="Servidor MIND:").grid(row=row, column=0, sticky="w", pady=4)
        self.e_server = ttk.Entry(f, width=50)
        self.e_server.insert(0, self.cfg.server_url)
        self.e_server.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1

        ttk.Label(f, text="Usuario:").grid(row=row, column=0, sticky="w", pady=4)
        self.e_user = ttk.Entry(f, width=50)
        self.e_user.insert(0, self.cfg.username)
        self.e_user.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1

        ttk.Label(f, text="Contraseña:").grid(row=row, column=0, sticky="w", pady=4)
        self.e_pass = ttk.Entry(f, width=50, show="*")
        self.e_pass.insert(0, self.cfg.password)
        self.e_pass.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1

        ttk.Label(f, text="ID del Cliente\n(opcional si eres\nsúper-admin):").grid(row=row, column=0, sticky="w", pady=4)
        self.e_tenant = ttk.Entry(f, width=50)
        self.e_tenant.insert(0, self.cfg.tenant_id)
        self.e_tenant.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1

        ttk.Label(f, text="Idioma:").grid(row=row, column=0, sticky="w", pady=4)
        self.cb_lang = ttk.Combobox(f, values=["es", "en"], state="readonly", width=6)
        self.cb_lang.set(self.cfg.language)
        self.cb_lang.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        # Dispositivos
        ttk.Label(f, text="Dispositivo MIC:").grid(row=row, column=0, sticky="w", pady=4)
        self.cb_mic = ttk.Combobox(f, values=[], width=50)
        self.cb_mic.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1

        ttk.Label(f, text="Loopback\n(sistema):").grid(row=row, column=0, sticky="w", pady=4)
        self.cb_lb = ttk.Combobox(f, values=[], width=50)
        self.cb_lb.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1

        ttk.Button(f, text="Escanear dispositivos", command=self._scan_devices).grid(row=row, column=1, sticky="w", pady=8)
        row += 1

        ttk.Button(f, text="Probar conexión y guardar", command=self._save_and_test).grid(row=row, column=1, sticky="w", pady=8)
        self._cfg_status = ttk.Label(f, text="", foreground="white")
        self._cfg_status.grid(row=row + 1, column=1, sticky="w", pady=4)

        self.tab_cfg.columnconfigure(1, weight=1)

    def _build_rec_tab(self):
        f = ttk.Frame(self.tab_rec, padding=12)
        f.pack(fill="both", expand=True)

        self._timer_label = ttk.Label(f, text="00:00:00", font=("Consolas", 36, "bold"))
        self._timer_label.pack(pady=12)

        self._status_label = ttk.Label(f, text="LISTO", foreground="#00e5a0")
        self._status_label.pack()

        btn_frame = ttk.Frame(f)
        btn_frame.pack(pady=12)

        self._btn_start = ttk.Button(btn_frame, text="● Grabar", command=self._start_recording, width=16)
        self._btn_start.pack(side="left", padx=8)

        self._btn_stop = ttk.Button(btn_frame, text="■ Finalizar", command=self._stop_recording, state="disabled", width=16)
        self._btn_stop.pack(side="left", padx=8)

        ttk.Label(f, text="Transcripción en vivo:").pack(anchor="w", pady=4)
        self._transcript_text = tk.Text(f, height=8, wrap="word", bg="#050505", fg="white",
                                         font=("Consolas", 10), state="disabled")
        self._transcript_text.pack(fill="both", expand=True, pady=4)

        self._chunk_label = ttk.Label(f, text="0 segmentos subidos")
        self._chunk_label.pack()

    # ── Acciones ────────────────────────────────────────────────────────────

    def _scan_devices(self):
        try:
            devices = sd.query_devices()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        names = [f"{i}: {d['name']}" for i, d in enumerate(devices) if d["max_input_channels"] > 0]
        self.cb_mic["values"] = names
        self.cb_lb["values"] = names
        if self._mic_dev_id is not None:
            self.cb_mic.set(f"{self._mic_dev_id}: {devices[self._mic_dev_id]['name']}")
        if self._device_id is not None:
            self.cb_lb.set(f"{self._device_id}: {devices[self._device_id]['name']}")

    def _save_and_test(self):
        self.cfg.server_url = self.e_server.get().strip()
        self.cfg.username = self.e_user.get().strip()
        self.cfg.password = self.e_pass.get()
        self.cfg.tenant_id = self.e_tenant.get().strip()
        self.cfg.language = self.cb_lang.get() or "es"

        # Resolver dispositivo del mic
        mic_txt = self.cb_mic.get()
        if mic_txt and ":" in mic_txt:
            idx = int(mic_txt.split(":")[0].strip())
            self._mic_dev_id = idx
            self.cfg.mic_device = sd.query_devices()[idx]["name"]
        # Resolver dispositivo loopback
        lb_txt = self.cb_lb.get()
        if lb_txt and ":" in lb_txt:
            idx = int(lb_txt.split(":")[0].strip())
            self._device_id = idx
            self.cfg.input_device = sd.query_devices()[idx]["name"]

        self.cfg.save()
        self._test_connection()

    def _test_connection(self):
        try:
            ok = self.api.login()
        except ConnectionError as e:
            self._cfg_status.configure(text=f"❌ {e}", foreground="red")
            return
        if ok:
            self._cfg_status.configure(text="✅ Conexión OK. Configuración guardada.", foreground="#00e5a0")
            self.notebook.select(self.tab_rec)

    def _start_recording(self):
        if self._recording:
            return
        # Verificar conexión
        try:
            self.api.login()
        except ConnectionError as e:
            messagebox.showerror("Error de conexión", str(e))
            return

        title = f"Grabación de escritorio {time.strftime('%Y-%m-%d %H:%M')}"
        try:
            meeting = self.api.create_meeting(title)
            self._meeting_id = meeting["id"]
        except requests.RequestException as e:
            messagebox.showerror("Error", f"No se pudo crear la reunión:\n{e}")
            return

        self._recording = True
        self._buffer = []
        self._seq = 0
        self._start_time = time.time()
        self._live_transcript = ""
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._status_label.configure(text="GRABANDO", foreground="red")
        self._transcript_text.configure(state="normal")
        self._transcript_text.delete("1.0", "end")
        self._transcript_text.configure(state="disabled")
        self._update_timer()

        # Iniciar captura de audio
        channels = 2  # mic + loopback
        devices = [self._mic_dev_id, self._device_id]
        try:
            self._stream = sd.InputStream(
                device=devices,
                channels=channels,
                samplerate=RATE,
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as e:
            messagebox.showerror("Error de audio",
                                 f"No se pudo iniciar la captura:\n{e}\n\n"
                                 "Verifica los dispositivos en Configuración → Escanear dispositivos.")
            self._recording = False
            self._btn_start.configure(state="normal")
            self._btn_stop.configure(state="disabled")
            return

        # Hilo para empaquetar y subir chunks cada CHUNK_SEC segundos
        self._thread = threading.Thread(target=self._upload_loop, daemon=True)
        self._thread.start()

    def _audio_callback(self, indata, frames, time_info, status):
        """Mezcla los dos canales (loopback + mic) a mono."""
        if not self._recording:
            return
        if status:
            pass
        mono = indata[:, 0] * 0.5 + indata[:, 1] * 0.5  # mezcla balanceada
        self._buffer.extend(mono.tolist())

    def _upload_loop(self):
        while self._recording:
            time.sleep(CHUNK_SEC)
            if len(self._buffer) < RATE * 0.4:
                continue
            chunk = self._buffer[:RATE * CHUNK_SEC]
            self._buffer = self._buffer[RATE * CHUNK_SEC:]

            silent = rms(chunk) < SILENCE_RMS
            wav = make_wav(chunk)
            try:
                self.api.upload_chunk(self._meeting_id, self._seq, wav, silent)
                self._seq += 1
                self.after(0, lambda: self._chunk_label.configure(text=f"{self._seq} segmentos subidos"))
                # Actualizar transcripción en vivo
                try:
                    t = self.api.get_transcript(self._meeting_id)
                    if t and t != self._live_transcript:
                        self._live_transcript = t
                        self.after(0, self._update_live_transcript)
                except Exception:
                    pass
            except requests.RequestException as e:
                # Reintentar una vez
                try:
                    time.sleep(2)
                    self.api.upload_chunk(self._meeting_id, self._seq, wav, silent)
                    self._seq += 1
                except Exception:
                    pass  # se pierde el chunk

    def _update_live_transcript(self):
        self._transcript_text.configure(state="normal")
        self._transcript_text.delete("1.0", "end")
        self._transcript_text.insert("1.0", self._live_transcript)
        self._transcript_text.see("end")
        self._transcript_text.configure(state="disabled")

    def _update_timer(self):
        if not self._recording:
            return
        elapsed = int(time.time() - self._start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self._timer_label.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.after(1000, self._update_timer)

    def _stop_recording(self):
        if not self._recording:
            return
        self._recording = False
        self._status_label.configure(text="FINALIZANDO…", foreground="white")

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # Esperar al hilo de subida
        if self._thread:
            self._thread.join(timeout=10)

        # Subir lo que quede en el buffer (< 5 s)
        if self._buffer and len(self._buffer) > RATE * 0.4:
            silent = rms(self._buffer) < SILENCE_RMS
            wav = make_wav(self._buffer)
            try:
                self.api.upload_chunk(self._meeting_id, self._seq, wav, silent)
                self._seq += 1
            except Exception:
                pass
            self._buffer = []

        # Finalizar la reunión
        try:
            self.api.finish_meeting(self._meeting_id)
            msg = f"✅ Reunión finalizada.\n\nAbrir en MIND:\n{self.cfg.server_url.rstrip('/')}/admin/reuniones/{self._meeting_id}"
            self._status_label.configure(text="FINALIZADA", foreground="#00e5a0")
            messagebox.showinfo("Reunión finalizada", msg)
        except Exception as e:
            self._status_label.configure(text=f"ERROR: {e}", foreground="red")

        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._timer_label.configure(text="00:00:00")

    def stop(self):
        if self._recording:
            self._stream = None  # evitar cerrar desde otro hilo
        self.destroy()


# ── Punto de entrada ─────────────────────────────────────────────────────────

def main():
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.stop)
    app.mainloop()


if __name__ == "__main__":
    main()