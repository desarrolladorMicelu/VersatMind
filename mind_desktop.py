"""
MIND Recorder — Asistente de escritorio (Windows / macOS / Linux)
===============================================================
Captura el audio del sistema (loopback WASAPI/Core Audio) + el micrófono en
paralelo con `soundcard`, los mezcla a mono y sube chunks WAV a la API de
MIND. Al finalizar, la reunión se transcribe con Deepgram + diarización.

`soundcard` se usa porque soporta loopback nativo del parlante por defecto
(insuperable en Windows; PortAudio/sounddevice no captura el sistema).

Instalación y build:
    pip install soundcard numpy requests pyinstaller
    pyinstaller --onefile --windowed --name "MIND Recorder" --collect-all soundcard --collect-all numpy mind_desktop.py
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import warnings
import wave
from pathlib import Path
from tkinter import ttk
from tkinter import messagebox
import tkinter as tk

import numpy as np
import requests
import soundcard as sc

warnings.filterwarnings("ignore")  # soundcard emite warnings de discontinuidad

__version__ = "1.3.0"
APP_NAME = "MIND Recorder"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / ".config")) / APP_NAME

RATE = 16000
BLOCK = 1600          # 100 ms a 16 kHz
CHUNK_SEC = 5
SILENCE_RMS = 0.01


# ── Utilidades de audio ─────────────────────────────────────────────────────

def rms(samples: np.ndarray) -> float:
    if samples is None or len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def make_wav(samples: np.ndarray) -> bytes:
    audio = np.clip(samples, -1.0, 1.0)
    pcm = (audio * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def list_input_mics() -> list[str]:
    """Micrófonos reales (sin loopback)."""
    return [m.name for m in sc.all_microphones(include_loopback=False)]


def list_loopback_devices() -> list[str]:
    """Dispositivos de loopback (parlantes capturados)."""
    return [
        m.name for m in sc.all_microphones(include_loopback=True)
        if getattr(m, "isloopback", False)
    ]


# ── Motor de captura (mic + loopback en paralelo, tasa nativa, downsampling manual) ──

RATE = 16000          # tasa de salida (la que esperan los chunks)
BLOCK = 400           # ~25 ms a 16 kHz (más frecuente evita overflow del buffer WASAPI)
CHUNK_SEC = 5


class CaptureEngine:
    def __init__(self, mic_name: str, loop_name: str):
        self.mic_name = mic_name
        self.loop_name = loop_name
        self._mic_buf: list[np.ndarray] = []
        self._loop_buf: list[np.ndarray] = []
        self._running = False
        self._threads: list[threading.Thread] = []
        self._errors: list[str] = []

    def _capture(self, name: str, include_loopback: bool, target: list):
        try:
            dev = sc.get_microphone(id=name, include_loopback=include_loopback)
            with dev.recorder(samplerate=RATE, channels=1) as rec:
                while self._running:
                    data = rec.record(numframes=BLOCK)
                    mono = np.asarray(data, dtype="float32")[:, 0]
                    target.append(mono)
        except Exception as e:  # noqa: BLE001
            self._errors.append(f"{name}: {e}")

    def start(self):
        self._running = True
        if self.mic_name:
            t = threading.Thread(
                target=self._capture, args=(self.mic_name, False, self._mic_buf), daemon=True,
            )
            t.start()
            self._threads.append(t)
        if self.loop_name:
            t = threading.Thread(
                target=self._capture, args=(self.loop_name, True, self._loop_buf), daemon=True,
            )
            t.start()
            self._threads.append(t)

    def flush(self) -> np.ndarray | None:
        """Extrae lo acumulado y mezcla (mic 0.5 + loopback 0.5)."""
        mic_arr = np.concatenate(self._mic_buf) if self._mic_buf else np.zeros(0, dtype="float32")
        loop_arr = np.concatenate(self._loop_buf) if self._loop_buf else np.zeros(0, dtype="float32")
        self._mic_buf.clear()
        self._loop_buf.clear()
        n = max(len(mic_arr), len(loop_arr))
        if n == 0:
            return None
        m = np.zeros(n, dtype="float32")
        m[: len(mic_arr)] = mic_arr
        l = np.zeros(n, dtype="float32")
        l[: len(loop_arr)] = loop_arr
        return m * 0.5 + l * 0.5

    def stop(self):
        self._running = False
        for t in self._threads:
            t.join(timeout=3)


# ── Configuración persistente ────────────────────────────────────────────────

class Config:
    def __init__(self):
        self.server_url = "https://mind.versat.com"
        self.username = ""
        self.password = ""
        self.tenant_id = ""
        self.language = "es"
        self.mic_device = ""
        self.loopback_device = ""
        self.load()

    @property
    def config_path(self) -> Path:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return CONFIG_DIR / "config.json"

    def load(self):
        p = self.config_path
        if not p.exists():
            return
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            self.server_url = d.get("server_url", self.server_url)
            self.username = d.get("username", "")
            self.password = d.get("password", "")
            self.tenant_id = str(d.get("tenant_id", ""))
            self.language = d.get("language", "es")
            self.mic_device = d.get("mic_device", "")
            self.loopback_device = d.get("loopback_device", "")
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
            "mic_device": self.mic_device,
            "loopback_device": self.loopback_device,
        }, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Cliente API ──────────────────────────────────────────────────────────────

class MindAPI:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = requests.Session()

    @property
    def base(self) -> str:
        return self.cfg.server_url.rstrip("/") + "/api/admin"

    def login(self) -> bool:
        try:
            resp = self.session.post(
                f"{self.base}/login",
                json={"username": self.cfg.username, "password": self.cfg.password},
                timeout=15,
            )
            if resp.status_code == 200:
                return True
            detail = (
                resp.json().get("detail")
                if resp.headers.get("content-type", "").startswith("application/json")
                else resp.text[:200]
            )
            raise ConnectionError(detail or f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            raise ConnectionError(str(e)) from e

    def create_meeting(self, title: str) -> dict:
        params = {"tenant_id": self.cfg.tenant_id} if self.cfg.tenant_id else {}
        resp = self.session.post(
            f"{self.base}/meetings",
            json={"title": title, "language": self.cfg.language,
                  "stt_provider": "deepgram", "diarize": True},
            params=params, timeout=15,
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
            f"{self.base}/meetings/{meeting_id}/finish", params=params, timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


# ── Ventana principal ────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{__version__}")
        self.resizable(False, False)
        self.configure(bg="#0d0d0d")
        self.option_add("*Font", ("Consolas", 11))

        self.cfg = Config()
        self.api = MindAPI(self.cfg)

        self._recording = False
        self._meeting: dict | None = None
        self._seq = 0
        self._engine: CaptureEngine | None = None
        self._thread: threading.Thread | None = None
        self._start_time: float = 0

        self._build_ui()
        self._scan_devices()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=16)
        self.tab_cfg = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_cfg, text="Configuración")
        self._build_config_tab()
        self.tab_rec = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_rec, text="Grabación")
        self._build_rec_tab()

    def _build_config_tab(self):
        f = ttk.Frame(self.tab_cfg, padding=12)
        f.pack(fill="both", expand=True)
        row = 0
        ttk.Label(f, text="Servidor MIND:").grid(row=row, column=0, sticky="w", pady=4)
        self.e_server = ttk.Entry(f, width=52)
        self.e_server.insert(0, self.cfg.server_url)
        self.e_server.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1
        ttk.Label(f, text="Usuario:").grid(row=row, column=0, sticky="w", pady=4)
        self.e_user = ttk.Entry(f, width=52)
        self.e_user.insert(0, self.cfg.username)
        self.e_user.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1
        ttk.Label(f, text="Contraseña:").grid(row=row, column=0, sticky="w", pady=4)
        self.e_pass = ttk.Entry(f, width=52, show="*")
        self.e_pass.insert(0, self.cfg.password)
        self.e_pass.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1
        ttk.Label(f, text="ID Cliente\n(opcional):").grid(row=row, column=0, sticky="w", pady=4)
        self.e_tenant = ttk.Entry(f, width=52)
        self.e_tenant.insert(0, self.cfg.tenant_id)
        self.e_tenant.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1
        ttk.Label(f, text="Idioma:").grid(row=row, column=0, sticky="w", pady=4)
        self.cb_lang = ttk.Combobox(f, values=["es", "en"], state="readonly", width=6)
        self.cb_lang.set(self.cfg.language)
        self.cb_lang.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1
        ttk.Separator(f, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="we", pady=8)
        row += 1
        ttk.Label(f, text="Micrófono\n(tu voz):").grid(row=row, column=0, sticky="w", pady=4)
        self.cb_mic = ttk.Combobox(f, values=[], width=52, state="readonly")
        self.cb_mic.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1
        ttk.Label(f, text="Audio del sistema\n(la reunión):").grid(row=row, column=0, sticky="w", pady=4)
        self.cb_lb = ttk.Combobox(f, values=[], width=52, state="readonly")
        self.cb_lb.grid(row=row, column=1, sticky="we", padx=8, pady=4)
        row += 1
        ttk.Button(f, text="Actualizar dispositivos", command=self._scan_devices).grid(row=row, column=1, sticky="w", pady=6)
        row += 1
        ttk.Button(f, text="Probar conexión y guardar", command=self._save_and_test).grid(row=row, column=1, sticky="w", pady=6)
        self._cfg_status = ttk.Label(f, text="", foreground="white", wraplength=420)
        self._cfg_status.grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=4)
        self.tab_cfg.columnconfigure(1, weight=1)

    def _build_rec_tab(self):
        f = ttk.Frame(self.tab_rec, padding=12)
        f.pack(fill="both", expand=True)
        self._create_frame = ttk.Frame(f)
        self._create_frame.pack(fill="x", pady=6)
        ttk.Label(self._create_frame, text="Título de la reunión:").pack(anchor="w")
        self._e_rec_title = ttk.Entry(self._create_frame, width=60)
        self._e_rec_title.insert(0, f"Reunión {time.strftime('%Y-%m-%d %H:%M')}")
        self._e_rec_title.pack(fill="x", pady=4)
        self._btn_create = ttk.Button(self._create_frame, text="Crear reunión", command=self._create_meeting)
        self._btn_create.pack(anchor="w", pady=4)
        self._lbl_meeting = ttk.Label(self._create_frame, text="", foreground="#00e5a0")
        self._lbl_meeting.pack(anchor="w")

        self._rec_frame = ttk.Frame(f)
        self._timer_label = ttk.Label(self._rec_frame, text="00:00:00", font=("Consolas", 36, "bold"))
        self._timer_label.pack(pady=8)
        self._status_label = ttk.Label(self._rec_frame, text="LISTO PARA GRABAR", foreground="#00e5a0")
        self._status_label.pack()
        btn_f = ttk.Frame(self._rec_frame)
        btn_f.pack(pady=8)
        self._btn_start = ttk.Button(btn_f, text="● Comenzar grabación", command=self._start_recording, width=22)
        self._btn_start.pack(side="left", padx=6)
        self._btn_stop = ttk.Button(btn_f, text="■ Finalizar", command=self._stop_recording, state="disabled", width=22)
        self._btn_stop.pack(side="left", padx=6)
        self._btn_reset = ttk.Button(btn_f, text="✕ Nueva reunión", command=self._reset_rec_state, width=14)
        self._btn_reset.pack(side="left", padx=6)
        ttk.Label(self._rec_frame, text="Registro:").pack(anchor="w", pady=4)
        self._log_text = tk.Text(self._rec_frame, height=8, wrap="word", bg="#050505",
                                 fg="white", font=("Consolas", 10), state="disabled")
        self._log_text.pack(fill="both", expand=True, pady=4)
        self._chunk_label = ttk.Label(self._rec_frame, text="0 segmentos subidos")
        self._chunk_label.pack()
        ttk.Label(self._rec_frame, text="Al finalizar, se procesa con Deepgram + "
                   "diarización (Speaker 0/1) y el resumen en MIND.",
                  foreground="#888", wraplength=460, justify="left").pack(anchor="w", pady=6)

    # ── Dispositivos ─────────────────────────────────────────────────────────

    def _scan_devices(self):
        try:
            mics = list_input_mics()
            loops = list_loopback_devices()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Error de audio", f"No se pudieron listar dispositivos:\n{e}")
            return

        self.cb_mic["values"] = mics
        self.cb_lb["values"] = loops
        self.cb_mic.set(self.cfg.mic_device if self.cfg.mic_device in mics else (mics[0] if mics else ""))
        self.cb_lb.set(self.cfg.loopback_device if self.cfg.loopback_device in loops else (loops[0] if loops else ""))
        if not loops:
            self._append_log("⚠ No se detectó dispositivo de loopback (audio del sistema).")

    # ── Acciones ─────────────────────────────────────────────────────────────

    def _save_and_test(self):
        self.cfg.server_url = self.e_server.get().strip()
        self.cfg.username = self.e_user.get().strip()
        self.cfg.password = self.e_pass.get()
        self.cfg.tenant_id = self.e_tenant.get().strip()
        self.cfg.language = self.cb_lang.get() or "es"
        self.cfg.mic_device = self.cb_mic.get().strip()
        self.cfg.loopback_device = self.cb_lb.get().strip()
        self.cfg.save()
        try:
            self.api.login()
        except ConnectionError as e:
            self._cfg_status.configure(text=f"❌ {e}", foreground="red")
            return
        self._cfg_status.configure(text="✅ Conexión OK. Configuración guardada.", foreground="#00e5a0")
        self.notebook.select(self.tab_rec)

    # ── Grabación ────────────────────────────────────────────────────────────

    def _create_meeting(self):
        if self._meeting is not None:
            return
        title = self._e_rec_title.get().strip()
        if not title:
            messagebox.showerror("Título requerido", "Ingresa un título para la reunión.")
            return
        try:
            m = self.api.create_meeting(title)
        except requests.RequestException as e:
            messagebox.showerror("Error", f"No se pudo crear la reunión:\n{e}")
            return
        self._meeting = m
        self._lbl_meeting.configure(text=f"✅ Reunión #{m['id']} — {m['title']}")
        self._btn_create.configure(state="disabled")
        self._e_rec_title.configure(state="disabled")
        self._rec_frame.pack(fill="both", expand=True, pady=6)
        self._status_label.configure(text="LISTO PARA GRABAR", foreground="#00e5a0")
        self._btn_start.configure(state="normal")
        self._append_log(f"Reunión #{m['id']} lista para grabar")

    def _reset_rec_state(self):
        self._recording = False
        self._meeting = None
        self._engine = None
        self._seq = 0
        self._rec_frame.forget()
        self._btn_create.configure(state="normal")
        self._e_rec_title.configure(state="normal")
        self._e_rec_title.delete(0, "end")
        self._e_rec_title.insert(0, f"Reunión {time.strftime('%Y-%m-%d %H:%M')}")
        self._lbl_meeting.configure(text="")
        self._chunk_label.configure(text="0 segmentos subidos")
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        self._timer_label.configure(text="00:00:00")

    def _append_log(self, text: str):
        self._log_text.configure(state="normal")
        self._log_text.insert("end", text + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _start_recording(self):
        if self._recording or self._meeting is None:
            return
        if not self.cfg.mic_device and not self.cfg.loopback_device:
            messagebox.showerror("Sin dispositivos", "Configura micrófono y/o audio del sistema.")
            return

        self._engine = CaptureEngine(self.cfg.mic_device, self.cfg.loopback_device)
        self._engine.start()
        time.sleep(0.5)
        if self._engine._errors:
            errs = "; ".join(self._engine._errors)
            messagebox.showerror("Error de audio", f"Fallo al iniciar captura:\n{errs}")
            self._engine.stop()
            self._engine = None
            return

        self._recording = True
        self._seq = 0
        self._start_time = time.time()
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._status_label.configure(text="GRABANDO", foreground="red")
        self._append_log(f"Mic: {self.cfg.mic_device or '(ninguno)'}")
        self._append_log(f"Sistema: {self.cfg.loopback_device or '(ninguno)'}")
        self._update_timer()
        self._thread = threading.Thread(target=self._upload_loop, daemon=True)
        self._thread.start()

    def _upload_loop(self):
        while self._recording and self._engine is not None:
            time.sleep(CHUNK_SEC)
            for e in self._engine._errors:
                self.after(0, lambda err=e: self._append_log(f"⚠ {err}"))
            self._engine._errors.clear()
            self._upload_pending()

    def _upload_pending(self):
        mixed = self._engine.flush() if self._engine else None
        if mixed is None or len(mixed) < RATE * 0.4:
            return
        silent = rms(mixed) < SILENCE_RMS
        wav = make_wav(mixed)
        mid = self._meeting["id"]
        try:
            self.api.upload_chunk(mid, self._seq, wav, silent)
            seq = self._seq
            self._seq += 1
            self.after(0, lambda: self._chunk_label.configure(text=f"{self._seq} segmentos subidos"))
            self.after(0, lambda: self._append_log(f"Seg {seq}" + (" (silencio)" if silent else "")))
        except requests.RequestException:
            try:
                time.sleep(2)
                self.api.upload_chunk(mid, self._seq, wav, silent)
                self._seq += 1
            except requests.RequestException:
                self.after(0, lambda: self._append_log("⚠ se perdió un segmento"))

    def _update_timer(self):
        if not self._recording:
            return
        elapsed = int(time.time() - self._start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self._timer_label.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.after(1000, self._update_timer)

    def _stop_recording(self):
        if not self._recording or self._meeting is None:
            return
        self._recording = False
        self._status_label.configure(text="FINALIZANDO…", foreground="white")

        if self._thread:
            self._thread.join(timeout=8)
        if self._engine:
            self._engine.stop()
            self._upload_pending()
            self._engine = None

        mid = self._meeting["id"]
        try:
            self.api.finish_meeting(mid)
            self._status_label.configure(text="FINALIZADA", foreground="#00e5a0")
            self._append_log("Reunión finalizada. Deepgram procesa diarización…")
            msg = (
                "✅ Reunión finalizada.\n\n"
                "En unos segundos estará lista con la transcripción "
                "etiquetada (Speaker 0/1) y el resumen.\n\n"
                f"{self.cfg.server_url.rstrip('/')}/admin/reuniones/{mid}"
            )
            messagebox.showinfo("Reunión finalizada", msg)
        except Exception as e:  # noqa: BLE001
            self._status_label.configure(text=f"ERROR: {e}", foreground="red")
            self._append_log(f"❌ {e}")

        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="disabled")

    def stop(self):
        self._recording = False
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
        self.destroy()


# ── Punto de entrada ─────────────────────────────────────────────────────────

def main():
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.stop)
    app.mainloop()


if __name__ == "__main__":
    main()