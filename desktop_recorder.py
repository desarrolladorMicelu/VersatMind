"""Compañero de escritorio MIND — grabación con loopback + mic.
Uso: python desktop_recorder.py
Captura audio del sistema (Zoom/Teams/Meet) + tu micrófono, los mezcla y
sube a la API de MIND como chunks WAV de 5 s.

Sin pagar nada extra: solo sounddevice (PortAudio, MIT) + requests.
Instalación: pip install sounddevice requests
"""
import io
import struct
import time
import wave

import requests
import sounddevice as sd

API_BASE = "http://localhost:8000/api/admin/meetings"
TENANT_ID = 4
COOKIE = {"admin_token": "..."}  # copia del navegador o login manual

CHUNK_SEC = 5
RATE = 16000

# Listar dispositivos para elegir los correctos:
# print(sd.query_devices())
# Busca un "Loopback" (Windows) o "Monitor of" (Linux) o "System" (macOS)
INPUT_DEVICE = None       # micrófono (None = default input)
LOOPBACK_DEVICE = None    # loopback (None = no loopback, solo mic)
# En Windows sería algo como:
# LOOPBACK_DEVICE = sd.query_devices()["Windows WASAPI"][3]


def make_wav_chunk(samples_mono: list[float]) -> bytes:
    """Codifica PCM mono 16-bit 16 kHz a WAV."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32768, min(32767, int(s * 32767))))
            for s in samples_mono
        ))
    return buf.getvalue()


def main():
    meeting = requests.post(
        f"{API_BASE}",
        json={"title": "Reunión desde escritorio", "language": "es"},
        cookies=COOKIE,
        params={"tenant_id": TENANT_ID},
    ).json()
    meeting_id = meeting["id"]
    print(f"Reunión {meeting_id} creada.")

    def callback(indata, frames, time_info, status):
        """indata.shape = (frames, canales). Mezcla a mono."""
        global buffer
        if status:
            pass
        mono = indata.mean(axis=1)  # mezclar canales
        buffer.extend(mono.tolist())

    buffer: list[float] = []
    seq = 0

    with sd.InputStream(
        device=INPUT_DEVICE,
        channels=2 if LOOPBACK_DEVICE else 1,
        samplerate=RATE,
        callback=callback,
    ):
        print("Grabando... Enter para finalizar.")
        while True:
            time.sleep(CHUNK_SEC)
            if len(buffer) < RATE * 0.5:
                continue
            chunk = buffer[: RATE * CHUNK_SEC]
            buffer = buffer[RATE * CHUNK_SEC:]
            wav = make_wav_chunk(chunk)
            resp = requests.post(
                f"{API_BASE}/{meeting_id}/chunks",
                cookies=COOKIE,
                params={"tenant_id": TENANT_ID},
                files={"audio": (f"c-{seq}.wav", wav, "audio/wav")},
                data={"seq": seq, "duration_ms": CHUNK_SEC * 1000, "silent": "0"},
            )
            if resp.ok:
                print(f"  chunk {seq} subido")
            seq += 1

    resp = requests.post(
        f"{API_BASE}/{meeting_id}/finish",
        cookies=COOKIE,
        params={"tenant_id": TENANT_ID},
    )
    print(f"Reunión finalizada: {resp.json()}")


if __name__ == "__main__":
    main()