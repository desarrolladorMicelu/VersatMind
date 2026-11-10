"""Resumen estructurado de reuniones con el LLM configurado."""
from __future__ import annotations

import json
import logging
import re

from mind.config import settings

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Eres un asistente de tomador de apuntes. A partir de la
transcripción de una reunión, genera un resumen estructurado en JSON con
exactamente estas claves:
{{
  "resumen_general": "resumen en 3-5 frases de TODO lo hablado, aunque no haya decisiones",
  "puntos_clave": ["listado de ideas o temas relevantes de la reunión"],
  "decisiones": ["decisiones tomadas"],
  "tareas": [{{"tarea": "descripción", "responsable": "persona o área"}}]
}}
Responde ÚNICAMENTE con el JSON, sin texto adicional. `resumen_general` es
obligatorio y resume la conversación completa. Si no hay decisiones o tareas,
usa listas vacías en esas claves."""

# Segunda pasada si la primera devolvió vacío: la transcripción pudo traer ruido.
RETRY_PROMPT = """La transcripción que recibiste pudo contener música, subtítulos o
frases sin contenido (por ejemplo anuncios de "suscríbete" o "subtítulos por
Amara.org"). Ignora ese ruido y extrae ÚNICAMENTE el contenido que parezca de
una reunión o conversación real. Responde en JSON:
{{"resumen_general": "...", "puntos_clave": [], "decisiones": [], "tareas": []}}
`resumen_general` resume lo escuchado en 3-5 frases; si no hay absolutamente
nada rescatable, devuelve listas vacías y resumen_general vacío. Responde solo el JSON."""


def _extract_json(text: str) -> dict:
    """Extrae el primer objeto JSON del texto (tolerante a markdown/muletillas)."""
    empty = {"resumen_general": "", "puntos_clave": [], "decisiones": [], "tareas": []}
    if not text:
        return dict(empty)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    raw = match.group(0) if match else text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = json.loads(raw.replace("\\n", "\n"))
        except json.JSONDecodeError:
            logger.warning("Resumen no parseable como JSON (%.200s)", text)
            return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    return {
        "resumen_general": (data.get("resumen_general") or "").strip(),
        "puntos_clave": data.get("puntos_clave") or [],
        "decisiones": data.get("decisiones") or [],
        "tareas": data.get("tareas") or [],
    }


async def generate_summary(transcript: str) -> dict:
    """Genera el resumen estructurado a partir del transcript completo."""
    from openai import AsyncOpenAI

    transcript = (transcript or "").strip()
    if not transcript:
        return {"resumen_general": "", "puntos_clave": [], "decisiones": [], "tareas": []}

    max_chars = 200_000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars]

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )

    messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": f"Transcripción de la reunión:\n\n{transcript}"},
    ]
    content: str | None = None
    for attempt in range(2):
        try:
            # JSON mode: fuerza salida validamente JSON (si el proveedor lo apoya)
            kwargs: dict = {"model": settings.OPENAI_MODEL, "temperature": 0.2, "messages": messages}
            if attempt == 0:
                kwargs["response_format"] = {"type": "json_object"}
            resp = await client.chat.completions.create(**kwargs)
            if resp.choices:
                content = resp.choices[0].message.content
                if content:
                    break
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Intento %d/2 resumen falló (%s); reintento sin json_object",
                attempt + 1, type(exc).__name__,
            )
            content = None

    result = _extract_json(content or "")
    # Segunda pasada si salió vacío: ayuda a rescatar contenido de una
    # transcripción ruidosa (música, subtítulos, interjecciones).
    if not any(result.values()) and len(transcript) > 40:
        logger.info("Resumen vacío en 1ª pasada; reintentando con limpieza de ruido")
        retry_messages = [
            {"role": "system", "content": RETRY_PROMPT},
            {"role": "user", "content": f"Transcripción:\n\n{transcript}"},
        ]
        try:
            resp = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                temperature=0.1,
                messages=retry_messages,
                response_format={"type": "json_object"},
            )
            retry_content = resp.choices[0].message.content if resp.choices else None
            retry_result = _extract_json(retry_content or "")
            if any(retry_result.values()):
                result = retry_result
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reintento de resumen falló: %s", type(exc).__name__)

    logger.info(
        "Resumen generado: puntos_clave=%d decisiones=%d tareas=%d",
        len(result["puntos_clave"]), len(result["decisiones"]), len(result["tareas"]),
    )
    if not any(result.values()):
        logger.warning(
            "Resumen vacío. Respuesta cruda del modelo: %.300s", content or "(vacía)",
        )
    return result