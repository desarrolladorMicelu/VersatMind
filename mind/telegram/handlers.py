"""
Handlers de mensajes y callbacks de Telegram para Mind by Versat.
Multi-tenant: el tenant se resuelve por el bot_token del mensaje entrante.
"""
from __future__ import annotations

import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096
ERROR_MSG = "Lo siento, ocurrió un error procesando tu solicitud. Por favor intenta de nuevo."


def _resolve_tenant(bot_token: str):
    """Resuelve el tenant por bot_token desde la caché en memoria."""
    from mind.tenants.resolver import resolve_by_token
    return resolve_by_token(bot_token)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal para mensajes de texto."""
    from mind.auth.authorization import check_access, WhitelistUnavailableError
    from mind.audit.logger import log_unauthorized
    from mind.db.base import _session_factory
    from mind.telegram.bot import send_text, send_document

    if update.message is None or update.message.text is None:
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id if update.message.from_user else 0
    username = update.message.from_user.username if update.message.from_user else None
    first_name = update.message.from_user.first_name if update.message.from_user else None
    text = update.message.text
    bot_token = context.bot.token

    # Resolver tenant
    tenant = _resolve_tenant(bot_token)
    if tenant is None:
        logger.error("No se encontró tenant para bot token ...%s", bot_token[-6:])
        await update.message.reply_text(ERROR_MSG)
        return

    if len(text) > MAX_MESSAGE_LENGTH:
        await update.message.reply_text(
            "Tu mensaje es demasiado largo. Por favor envíalo en partes (máximo 4096 caracteres)."
        )
        return

    if _session_factory is None:
        await update.message.reply_text(ERROR_MSG)
        return

    # Verificar autorización (scoped por tenant)
    try:
        async with _session_factory() as session:
            auth_result = await check_access(chat_id, tenant.id, session)
    except WhitelistUnavailableError:
        await update.message.reply_text(
            "El servicio no está disponible en este momento. Por favor intenta de nuevo en unos minutos."
        )
        return
    except Exception:
        await update.message.reply_text(ERROR_MSG)
        return

    # Usuario no autorizado → flujo de solicitud de acceso
    if not auth_result.allowed:
        await log_unauthorized(chat_id, user_id, text, tenant_id=tenant.id)
        await _handle_access_request(
            update=update,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            tenant=tenant,
        )
        return

    # Usuario autorizado → procesar con el agente
    try:
        async with _session_factory() as session:
            from mind.agent.orchestrator import process
            agent_result = await process(
                message=text,
                chat_id=chat_id,
                tenant=tenant,
                auth_result=auth_result,
                session=session,
            )
    except Exception as exc:
        logger.error("Error en orchestrator tenant=%s chat_id=%s: %s", tenant.slug, chat_id, exc)
        await update.message.reply_text(ERROR_MSG)
        return

    # Enviar respuesta de texto
    response_text = agent_result.text or ERROR_MSG
    try:
        await send_text(chat_id, response_text, bot_token)
    except Exception:
        try:
            await update.message.reply_text(response_text)
        except Exception:
            pass

    # Enviar archivo si existe
    if agent_result.file_path:
        try:
            await send_document(
                chat_id=chat_id,
                file_path=agent_result.file_path,
                bot_token=bot_token,
                caption=agent_result.file_caption or "Aquí está tu informe.",
            )
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ No pude enviar el archivo: {exc}")
        except Exception:
            await update.message.reply_text(
                "⚠️ El informe fue generado pero no pude enviarlo. Por favor intenta de nuevo."
            )
        finally:
            if os.path.exists(agent_result.file_path):
                try:
                    os.unlink(agent_result.file_path)
                    tmp_dir = os.path.dirname(agent_result.file_path)
                    if os.path.isdir(tmp_dir) and not os.listdir(tmp_dir):
                        os.rmdir(tmp_dir)
                except Exception:
                    pass


async def _handle_access_request(
    update: Update,
    chat_id: int,
    user_id: int,
    username: str | None,
    first_name: str | None,
    tenant,
) -> None:
    """Flujo cuando un usuario no autorizado escribe al bot."""
    from mind.db.base import _session_factory
    from mind.auth.access_requests import get_or_create_request
    from mind.telegram.bot import get_application

    if _session_factory is None:
        await update.message.reply_text(ERROR_MSG)
        return

    async with _session_factory() as session:
        _, is_new = await get_or_create_request(
            chat_id=chat_id,
            tenant_id=tenant.id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            session=session,
        )
        await session.commit()

    await update.message.reply_text(
        "👋 Hola! No tienes acceso a este servicio aún.\n\n"
        "Tu solicitud fue enviada al administrador. "
        "Te notificaremos cuando sea aprobada."
    )

    if not is_new:
        return

    user_display = f"@{username}" if username else first_name or f"ID: {chat_id}"
    name_display = first_name or "Sin nombre"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Aprobar", callback_data=f"approve:{tenant.id}:{chat_id}"),
            InlineKeyboardButton("❌ Rechazar", callback_data=f"reject:{tenant.id}:{chat_id}"),
        ]
    ])

    admin_msg = (
        f"🔔 *Nueva solicitud de acceso*\n\n"
        f"🏢 Tenant: {tenant.name}\n"
        f"👤 Nombre: {name_display}\n"
        f"📱 Usuario: {user_display}\n"
        f"🆔 Chat ID: `{chat_id}`\n\n"
        f"¿Deseas aprobar el acceso?"
    )

    try:
        app = get_application(tenant.bot_token)
        await app.bot.send_message(
            chat_id=tenant.admin_chat_id,
            text=admin_msg,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception as exc:
        logger.error(
            "No se pudo notificar al admin tenant=%s sobre chat_id=%s: %s",
            tenant.slug, chat_id, exc,
        )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja los clicks en los botones inline de aprobación/rechazo."""
    from mind.db.base import _session_factory
    from mind.auth.access_requests import approve_user, reject_request
    from mind.telegram.bot import get_application
    from mind.tenants.resolver import resolve_by_id

    query = update.callback_query
    await query.answer()

    if not query.data or query.data.count(":") < 2:
        return

    parts = query.data.split(":", 2)
    action = parts[0]
    tenant_id = int(parts[1])
    target_chat_id = int(parts[2])

    tenant = resolve_by_id(tenant_id)
    if tenant is None:
        await query.edit_message_text("❌ Error: tenant no encontrado.")
        return

    # Solo el admin del tenant puede ejecutar estas acciones
    if query.from_user.id != tenant.admin_chat_id:
        await query.answer("No tienes permiso para hacer esto.", show_alert=True)
        return

    if _session_factory is None:
        await query.edit_message_text("❌ Error: base de datos no disponible.")
        return

    app = get_application(tenant.bot_token)

    if action == "approve":
        async with _session_factory() as session:
            user = await approve_user(target_chat_id, tenant_id, session)
            await session.commit()

        if user:
            username_display = f"@{user.username}" if user.username else f"ID: {target_chat_id}"
            await query.edit_message_text(
                f"✅ Usuario {username_display} aprobado correctamente."
            )
            try:
                await app.bot.send_message(
                    chat_id=target_chat_id,
                    text=(
                        "🎉 ¡Tu solicitud fue aprobada!\n\n"
                        "Ya puedes usar Mind. Escríbeme lo que necesitas."
                    ),
                )
            except Exception as exc:
                logger.error(
                    "No se pudo notificar al usuario aprobado %s tenant=%s: %s",
                    target_chat_id, tenant.slug, exc,
                )
        else:
            await query.edit_message_text("⚠️ No se encontró solicitud pendiente para este usuario.")

    elif action == "reject":
        async with _session_factory() as session:
            rejected = await reject_request(target_chat_id, tenant_id, session)
            await session.commit()

        if rejected:
            await query.edit_message_text(f"❌ Solicitud de ID {target_chat_id} rechazada.")
            try:
                await app.bot.send_message(
                    chat_id=target_chat_id,
                    text=(
                        "Lo sentimos, tu solicitud de acceso fue rechazada. "
                        "Contacta al administrador si crees que es un error."
                    ),
                )
            except Exception as exc:
                logger.error(
                    "No se pudo notificar al usuario rechazado %s tenant=%s: %s",
                    target_chat_id, tenant.slug, exc,
                )
        else:
            await query.edit_message_text("⚠️ No se encontró solicitud pendiente para rechazar.")
