"""
Configuración del Bot de Telegram para Mind by Versat.
Requisitos: 1.1, 1.6, 1.7
"""
from __future__ import annotations

import asyncio
import logging
import os

from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters

logger = logging.getLogger(__name__)

_application: Application | None = None


def get_application() -> Application:
    if _application is None:
        raise RuntimeError("Bot no inicializado. Llama a init_bot() primero.")
    return _application


def init_bot(token: str) -> Application:
    """Construye y retorna la Application de python-telegram-bot."""
    global _application
    from mind.telegram.handlers import message_handler as _msg_handler
    from mind.telegram.handlers import callback_handler as _cb_handler
    from telegram.ext import CallbackQueryHandler

    _application = (
        Application.builder()
        .token(token)
        .build()
    )
    # Handler para mensajes de texto (no comandos)
    _application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, _msg_handler)
    )
    # Handler para botones inline (aprobar/rechazar)
    _application.add_handler(
        CallbackQueryHandler(_cb_handler)
    )
    return _application


async def setup_webhook(base_url: str, token: str) -> None:
    """
    Registra el webhook en Telegram API.
    base_url debe ser la URL pública del servicio (Railway o ngrok).
    """
    app = get_application()
    webhook_url = f"{base_url.rstrip('/')}/webhook"
    await app.bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message", "callback_query"],
    )
    logger.info("Webhook registrado en: %s", webhook_url)


async def process_update(update_data: dict) -> None:
    """Procesa un update de Telegram (llamado desde el endpoint /webhook)."""
    app = get_application()
    update = Update.de_json(update_data, app.bot)
    await app.process_update(update)


async def send_text(chat_id: int, text: str, parse_mode: str = "Markdown") -> None:
    """
    Envía un mensaje de texto al chat_id.
    Con retry básico para errores transitorios.
    Requisito: 1.1
    """
    app = get_application()
    for attempt in range(3):
        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
            )
            return
        except Exception as exc:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("send_text fallido para chat_id=%s tras 3 intentos: %s", chat_id, exc)
                raise


async def send_document(
    chat_id: int,
    file_path: str,
    caption: str = "",
) -> None:
    """
    Envía un archivo al chat_id.
    Valida tipo y tamaño antes de enviar.
    Requisito: 1.7
    """
    import os
    MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

    allowed_extensions = (".pdf", ".xlsx", ".xls")
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in allowed_extensions:
        raise ValueError(f"Tipo de archivo no permitido: {ext!r}. Solo PDF y Excel.")

    file_size = os.path.getsize(file_path)
    if file_size > MAX_SIZE_BYTES:
        raise ValueError(
            f"Archivo demasiado grande: {file_size / 1024 / 1024:.1f} MB. Máximo: 50 MB."
        )

    app = get_application()
    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                await app.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    caption=caption,
                )
            return
        except Exception as exc:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("send_document fallido para chat_id=%s: %s", chat_id, exc)
                raise
