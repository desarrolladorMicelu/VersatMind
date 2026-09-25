"""
Gestión de múltiples bots de Telegram — uno por tenant.
Cada tenant tiene su propia Application de python-telegram-bot.
"""
from __future__ import annotations

import asyncio
import logging

from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters

logger = logging.getLogger(__name__)

# Mapa token → Application
_applications: dict[str, Application] = {}


def get_application(bot_token: str) -> Application:
    app = _applications.get(bot_token)
    if app is None:
        raise RuntimeError(f"Bot no inicializado para token ...{bot_token[-6:]}")
    return app


def get_all_applications() -> dict[str, Application]:
    return _applications


def init_bot(bot_token: str) -> Application:
    """Construye e inicializa la Application para un tenant."""
    if bot_token in _applications:
        return _applications[bot_token]

    from mind.telegram.handlers import message_handler as _msg_handler
    from mind.telegram.handlers import callback_handler as _cb_handler

    app = (
        Application.builder()
        .token(bot_token)
        .build()
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _msg_handler))
    app.add_handler(CallbackQueryHandler(_cb_handler))

    _applications[bot_token] = app
    return app


async def setup_webhook(webhook_url: str, bot_token: str) -> None:
    """Registra el webhook para el bot del tenant y verifica que esté activo."""
    import asyncio
    app = get_application(bot_token)
    full_url = f"{webhook_url.rstrip('/')}/webhook/{bot_token}"

    # Intentar registrar hasta 3 veces
    for attempt in range(3):
        result = await app.bot.set_webhook(url=full_url)
        if result:
            break
        logger.warning(
            "Intento %d/3 — setWebhook falló para bot ...%s", attempt + 1, bot_token[-6:],
        )
        await asyncio.sleep(2)

    # Verificar que el webhook esté activo
    webhook_info = await app.bot.get_webhook_info()
    if webhook_info.url == full_url:
        logger.info(
            "Webhook OK para bot ...%s → %s (pendientes=%d)",
            bot_token[-6:], full_url, webhook_info.pending_update_count or 0,
        )
    else:
        logger.warning(
            "Webhook no coincide para bot ...%s — esperado=%s actual=%s",
            bot_token[-6:], full_url, webhook_info.url,
        )
        await app.bot.set_webhook(url=full_url)
        logger.info("Webhook re-registrado para bot ...%s", bot_token[-6:])


async def teardown_bot(bot_token: str) -> None:
    """Elimina el webhook y apaga la Application del tenant."""
    app = _applications.pop(bot_token, None)
    if app is None:
        return
    try:
        await app.bot.delete_webhook()
        await app.shutdown()
    except Exception as exc:
        logger.warning("Error apagando bot ...%s: %s", bot_token[-6:], exc)


async def process_update(update_data: dict, bot_token: str) -> None:
    """Procesa un update de Telegram para el bot del tenant correspondiente."""
    app = get_application(bot_token)
    update = Update.de_json(update_data, app.bot)
    await app.process_update(update)


_TELEGRAM_MAX_CHARS = 4096


async def send_text(
    chat_id: int,
    text: str,
    bot_token: str,
    parse_mode: str = "Markdown",
) -> None:
    """Envía un mensaje de texto via el bot del tenant. Divide en partes si excede 4096 caracteres."""
    app = get_application(bot_token)

    if len(text) <= _TELEGRAM_MAX_CHARS:
        await _send_single(chat_id, text, bot_token, app, parse_mode)
        return

    # Dividir en partes de hasta 4096 caracteres, cortando en \n
    parts: list[str] = []
    while text:
        if len(text) <= _TELEGRAM_MAX_CHARS:
            parts.append(text)
            break
        # Buscar el último \n antes del límite
        cut = text.rfind("\n", 0, _TELEGRAM_MAX_CHARS)
        if cut == -1:
            cut = _TELEGRAM_MAX_CHARS
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")

    for i, part in enumerate(parts):
        prefix = f"[{i+1}/{len(parts)}]\n" if len(parts) > 1 else ""
        try:
            await _send_single(chat_id, prefix + part, bot_token, app, parse_mode)
        except Exception as exc:
            logger.error(
                "send_text parte %d/%d fallido chat_id=%s: %s",
                i + 1, len(parts), chat_id, exc,
            )


async def _send_single(chat_id: int, text: str, bot_token: str, app, parse_mode: str) -> None:
    """Intenta enviar un mensaje con hasta 3 reintentos. Si falla por parse_mode, reintenta sin formato."""
    for attempt in range(3):
        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
            )
            return
        except Exception as exc:
            if "can't parse entities" in str(exc).lower() and attempt == 0:
                # Reintentar sin Markdown si falla el parseo
                return await _send_single(chat_id, text, bot_token, app, "")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error(
                    "send_text fallido chat_id=%s bot=...%s tras 3 intentos: %s",
                    chat_id, bot_token[-6:], exc,
                )
                raise


async def send_document(
    chat_id: int,
    file_path: str,
    bot_token: str,
    caption: str = "",
) -> None:
    """Envía un archivo via el bot del tenant."""
    import os
    MAX_SIZE_BYTES = 50 * 1024 * 1024

    allowed_extensions = (".pdf", ".xlsx", ".xls")
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in allowed_extensions:
        raise ValueError(f"Tipo de archivo no permitido: {ext!r}. Solo PDF y Excel.")

    file_size = os.path.getsize(file_path)
    if file_size > MAX_SIZE_BYTES:
        raise ValueError(
            f"Archivo demasiado grande: {file_size / 1024 / 1024:.1f} MB. Máximo: 50 MB."
        )

    app = get_application(bot_token)
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
                logger.error(
                    "send_document fallido chat_id=%s bot=...%s: %s",
                    chat_id, bot_token[-6:], exc,
                )
                raise
