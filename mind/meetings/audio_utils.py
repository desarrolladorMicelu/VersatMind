"""Utilidades de manipulación de audio."""
from __future__ import annotations


def merge_wav_chunks(chunk_data_list: list[bytes]) -> bytes:
    """
    Une chunks WAV (cada uno con cabecera de 44 bytes + PCM) en un único WAV
    válido con una sola cabecera. Los chunks originales son de 16 kHz mono
    16-bit PCM, grabados con Web Audio API.
    """
    payloads: list[bytes] = []
    total_data = 0
    sample_rate = 16000
    channels = 1
    bits = 16
    for data in chunk_data_list:
        if len(data) < 44 or data[:4] != b"RIFF":
            return b"".join(chunk_data_list)
        data_len = int.from_bytes(data[40:44], "little")
        payloads.append(data[44:44 + data_len])
        total_data += data_len
        if data_len == len(data) - 44:
            sample_rate = int.from_bytes(data[24:28], "little")
            channels = int.from_bytes(data[22:24], "little")
            bits = int.from_bytes(data[34:36], "little")

    byt = bits // 8
    header = bytearray(44)
    header[0:4] = b"RIFF"
    header[4:8] = (36 + total_data).to_bytes(4, "little")
    header[8:12] = b"WAVE"
    header[12:16] = b"fmt "
    header[16:20] = (16).to_bytes(4, "little")
    header[20:22] = (1).to_bytes(2, "little")
    header[22:24] = channels.to_bytes(2, "little")
    header[24:28] = sample_rate.to_bytes(4, "little")
    header[28:32] = (sample_rate * channels * byt).to_bytes(4, "little")
    header[32:34] = (channels * byt).to_bytes(2, "little")
    header[34:36] = bits.to_bytes(2, "little")
    header[36:40] = b"data"
    header[40:44] = total_data.to_bytes(4, "little")
    return bytes(header) + b"".join(payloads)