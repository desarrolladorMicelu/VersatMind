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


def _resolve_webhook_base(tenant_webhook_url: str | None) -> str:
    """
    Base pública del webhook. Prioriza TELEGRAM_WEBHOOK_URL (el host real del
    despliegue); si no está configurada usa la del tenant.
    """
    from mind.config import settings
    env_base = (settings.TELEGRAM_WEBHOOK_URL or "").strip()
    if env_base.startswith("http") and "example.com" not in env_base:
        return env_base.rstrip("/")
    if tenant_webhook_url and tenant_webhook_url.startswith("http"):
        return tenant_webhook_url.rstrip("/")
    return ""


def webhook_full_url(bot_token: str, tenant_webhook_url: str | None) -> str:
    base = _resolve_webhook_base(tenant_webhook_url)
    if not base:
        return ""
    return f"{base}/webhook/{bot_token}"


async def ensure_webhook(bot_token: str, tenant_webhook_url: str | None) -> bool:
    """
    Garantiza que el webhook del bot apunte a la URL pública correcta.
    Idempotente: si ya está bien, no hace nada. Devuelve True si queda correcto.
    """
    full_url = webhook_full_url(bot_token, tenant_webhook_url)
    if not full_url:
        logger.error(
            "No hay base de webhook configurada para bot ...%s "
            "(revisa TELEGRAM_WEBHOOK_URL o tenants.webhook_url)", bot_token[-6:],
        )
        return False

    app = get_application(bot_token)

    for attempt in range(3):
        try:
            info = await app.bot.get_webhook_info()
            if info.url == full_url:
                logger.info(
                    "Webhook OK para bot ...%s (pendientes=%d)",
                    bot_token[-6:], info.pending_update_count or 0,
                )
                return True
            await app.bot.set_webhook(url=full_url)
            info = await app.bot.get_webhook_info()
            if info.url == full_url:
                logger.info("Webhook registrado para bot ...%s → %s", bot_token[-6:], full_url)
                return True
            logger.warning(
                "Webhook no coincide para bot ...%s — esperado=%s actual=%s",
                bot_token[-6:], full_url, info.url,
            )
        except Exception as exc:
            logger.warning(
                "Intento %d/3 de webhook falló para bot ...%s: %s",
                attempt + 1, bot_token[-6:], exc,
            )
        await asyncio.sleep(2)

    logger.error("No se pudo asegurar el webhook para bot ...%s", bot_token[-6:])
    return False


async def setup_webhook(webhook_url: str, bot_token: str) -> bool:
    """Compatibilidad: registra/verifica el webhook del bot del tenant."""
    return await ensure_webhook(bot_token, webhook_url)


async def teardown_bot(bot_token: str) -> None:
    """
    Apaga la Application del tenant SIN borrar el webhook.

    El webhook se conserva en Telegram apuntando a la URL pública, así que
    sobrevive a reinicios y despliegues. Borrarlo aquí causaba que el bot
    dejara de responder tras cada push (y con despliegues solapados, que la
    instancia vieja borrara el webhook que la nueva acababa de registrar).
    """
    app = _applications.pop(bot_token, None)
    if app is None:
        return
    try:
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
