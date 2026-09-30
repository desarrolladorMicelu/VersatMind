"""
Registro de chats de Telegram que el bot ha visto (usuarios y grupos).

Se usa para ofrecer una lista de destinos amigable en los prompts
programados, sin que el administrador tenga que conocer el chat_id.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)


async def record_chat(tenant_id: int, chat, from_user=None) -> None:
    """
    Inserta o actualiza el chat en el registro del tenant.
    Tolerante a fallos: nunca debe romper el manejo del mensaje.
    """
    if chat is None:
        return
    try:
        from mind.db.base import _session_factory
        from mind.db.models import TelegramChat

        if _session_factory is None:
            return

        now = datetime.now(timezone.utc)
        chat_type = getattr(chat, "type", None) or "private"
        chat_id = getattr(chat, "id", None)
        if chat_id is None:
            return

        async with _session_factory() as session:
            row = (await session.execute(
                select(TelegramChat).where(
                    TelegramChat.tenant_id == tenant_id,
                    TelegramChat.chat_id == chat_id,
                )
            )).scalar_one_or_none()

            title = getattr(chat, "title", None)
            username = getattr(chat, "username", None)
            first_name = getattr(chat, "first_name", None)
            last_name = getattr(chat, "last_name", None)
            if from_user is not None:
                username = getattr(from_user, "username", None) or username
                first_name = getattr(from_user, "first_name", None) or first_name
                last_name = getattr(from_user, "last_name", None) or last_name

            if row is None:
                session.add(TelegramChat(
                    tenant_id=tenant_id,
                    chat_id=chat_id,
                    chat_type=chat_type,
                    title=title,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    last_seen_at=now,
                ))
            else:
                row.chat_type = chat_type
                row.last_seen_at = now
                if title:
                    row.title = title
                if username:
                    row.username = username
                if first_name:
                    row.first_name = first_name
                if last_name:
                    row.last_name = last_name
            await session.commit()
    except Exception as exc:
        logger.debug("No se pudo registrar el chat tenant=%s: %s", tenant_id, exc)
