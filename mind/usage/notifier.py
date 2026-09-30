"""
Notificaciones de consumo: avisa al administrador cuando un usuario supera
el umbral configurado. Soporta Telegram (bot del tenant) y, opcionalmente,
email vía SMTP (stdlib, sin dependencias nuevas).

Todas las funciones son tolerantes a fallos: nunca lanzan excepción hacia el
flujo del agente.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass
class UsageAlertNotification:
    tenant_id: int
    tenant_name: str
    bot_token: str | None
    admin_chat_id: int | None
    chat_id: int
    username: str | None
    user_id: int | None
    threshold_usd: float
    total_cost_usd: float
    total_tokens: int
    period_label: str
    paused: bool = False
    notify_telegram: bool = True
    notify_email: bool = False
    admin_email: str | None = None

    @property
    def user_display(self) -> str:
        if self.username:
            return f"@{self.username}"
        return f"ID: {self.chat_id}"


def _format_alert_message(n: UsageAlertNotification) -> str:
    pause_line = (
        "\n⏸️ El acceso del usuario fue *pausado automáticamente*."
        if n.paused
        else "\nPuedes pausar su acceso desde el panel de consumo."
    )
    return (
        "🚨 *Alerta de consumo de tokens*\n\n"
        f"🏢 Cliente: {n.tenant_name}\n"
        f"👤 Usuario: {n.user_display}\n"
        f"💰 Consumo: *${n.total_cost_usd:.2f} USD* (umbral ${n.threshold_usd:.2f})\n"
        f"🔢 Tokens: {n.total_tokens:,}\n"
        f"📅 Período: {n.period_label}\n"
        f"{pause_line}"
    )


async def _send_telegram(n: UsageAlertNotification) -> None:
    if not n.bot_token or not n.admin_chat_id:
        logger.warning(
            "Alerta de consumo sin bot_token/admin_chat_id tenant=%s", n.tenant_id
        )
        return
    from mind.telegram.bot import send_text

    await send_text(n.admin_chat_id, _format_alert_message(n), n.bot_token)


def _send_email_sync(n: UsageAlertNotification) -> None:
    from mind.config import settings

    if not (settings.SMTP_HOST and n.admin_email):
        logger.warning(
            "Notificación email solicitada pero SMTP no configurado tenant=%s", n.tenant_id
        )
        return

    msg = EmailMessage()
    msg["Subject"] = f"[Mind] Alerta de consumo — {n.tenant_name}"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = n.admin_email
    msg.set_content(
        _format_alert_message(n).replace("*", "").replace("_", "")
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_TLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


DEPLETED_MSG = (
    "⛔ Tu bolsa de tokens se agotó.\n\n"
    "El acceso a Mind está temporalmente pausado para tu usuario. "
    "Contacta al administrador de tu empresa para recargar tu bolsa y "
    "reactivar el servicio."
)

RESUMED_MSG = (
    "✅ Tu acceso a Mind fue reactivado.\n\n"
    "Tu bolsa de tokens fue recargada. Ya puedes volver a escribirme."
)


async def notify_user_paused(bot_token: str | None, chat_id: int) -> None:
    """Avisa al usuario que su acceso fue pausado por bolsa agotada."""
    if not bot_token:
        return
    try:
        from mind.telegram.bot import send_text
        await send_text(chat_id, DEPLETED_MSG, bot_token, parse_mode="")
    except Exception as exc:
        logger.warning("No se pudo notificar pausa al usuario %s: %s", chat_id, exc)


async def notify_user_resumed(bot_token: str | None, chat_id: int) -> None:
    """Avisa al usuario que su acceso fue reactivado."""
    if not bot_token:
        return
    try:
        from mind.telegram.bot import send_text
        await send_text(chat_id, RESUMED_MSG, bot_token, parse_mode="")
    except Exception as exc:
        logger.warning("No se pudo notificar reactivación al usuario %s: %s", chat_id, exc)


async def notify_usage_alert(n: UsageAlertNotification) -> None:
    """Envía la alerta por los canales habilitados. Nunca lanza excepción."""
    if n.notify_telegram:
        try:
            await _send_telegram(n)
        except Exception as exc:
            logger.warning(
                "No se pudo enviar alerta por Telegram tenant=%s chat_id=%s: %s",
                n.tenant_id, n.chat_id, exc,
            )

    if n.notify_email:
        try:
            await asyncio.to_thread(_send_email_sync, n)
        except Exception as exc:
            logger.warning(
                "No se pudo enviar alerta por email tenant=%s chat_id=%s: %s",
                n.tenant_id, n.chat_id, exc,
            )
