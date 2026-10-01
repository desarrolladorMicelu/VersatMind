"""
Interfaz web de chat (tipo Claude) para el panel de administración.

- Conversaciones guardadas por (tenant, owner).
- Cada conversación usa un chat_id sintético para reutilizar el historial
  persistido como memoria del agente.
- El endpoint de streaming (SSE) emite: status, tool, delta, done, error.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import get_effective_tenant_id, require_admin
from mind.db.base import get_session
from mind.db.models import ChatConversation, ConversationMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/chat", tags=["chat"])

# Base sintética para chat_ids de la web (fuera del rango de Telegram).
WEB_CHAT_BASE = -9_000_000_000_000_000


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationRename(BaseModel):
    title: str


class ChatStreamRequest(BaseModel):
    conversation_id: int
    message: str
    tenant_id: int | None = None


def _owner(admin: dict) -> str:
    return str(admin.get("sub") or "admin")


def _conv_dict(c: ChatConversation) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "chat_id": c.chat_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.get("/conversations")
async def list_conversations(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    tid = get_effective_tenant_id(admin, tenant_id)
    rows = (await session.execute(
        select(ChatConversation)
        .where(ChatConversation.tenant_id == tid, ChatConversation.owner == _owner(admin))
        .order_by(ChatConversation.updated_at.desc())
    )).scalars().all()
    return [_conv_dict(c) for c in rows]


@router.post("/conversations")
async def create_conversation(
    body: ConversationCreate | None = Body(default=None),
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    tid = get_effective_tenant_id(admin, tenant_id)
    title = (body.title if body and body.title else "Nueva conversación").strip() or "Nueva conversación"
    conv = ChatConversation(
        tenant_id=tid,
        owner=_owner(admin),
        title=title[:80],
        chat_id=0,
    )
    session.add(conv)
    await session.flush()
    conv.chat_id = WEB_CHAT_BASE - conv.id
    await session.commit()
    await session.refresh(conv)
    return _conv_dict(conv)


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: int,
    body: ConversationRename,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    tid = get_effective_tenant_id(admin, tenant_id)
    conv = (await session.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.tenant_id == tid,
            ChatConversation.owner == _owner(admin),
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv.title = (body.title or "").strip()[:80] or conv.title
    await session.commit()
    return _conv_dict(conv)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    tid = get_effective_tenant_id(admin, tenant_id)
    conv = (await session.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.tenant_id == tid,
            ChatConversation.owner == _owner(admin),
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    await session.execute(
        delete(ConversationMessage).where(
            ConversationMessage.tenant_id == tid,
            ConversationMessage.chat_id == conv.chat_id,
        )
    )
    await session.delete(conv)
    await session.commit()
    return {"ok": True}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    tid = get_effective_tenant_id(admin, tenant_id)
    conv = (await session.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.tenant_id == tid,
            ChatConversation.owner == _owner(admin),
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    rows = (await session.execute(
        select(ConversationMessage)
        .where(
            ConversationMessage.tenant_id == tid,
            ConversationMessage.chat_id == conv.chat_id,
        )
        .order_by(ConversationMessage.created_at.asc())
    )).scalars().all()

    return [
        {
            "id": r.id,
            "role": r.role,
            "content": r.content,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
        if r.role in ("user", "assistant")
    ]


@router.post("/stream")
async def chat_stream(
    body: ChatStreamRequest,
    admin=Depends(require_admin),
    tenant_id: int | None = Query(default=None),
):
    tid = get_effective_tenant_id(admin, tenant_id if tenant_id is not None else body.tenant_id)
    owner = _owner(admin)
    message = (body.message or "").strip()

    async def event_gen():
        from mind.db.base import _session_factory
        from mind.tenants.resolver import resolve_by_id
        from mind.agent.streaming import stream_chat
        from mind.auth.authorization import AuthResult, Permission

        if not message:
            yield _sse({"type": "error", "message": "El mensaje está vacío."})
            return
        if _session_factory is None:
            yield _sse({"type": "error", "message": "Base de datos no disponible."})
            return

        tenant = resolve_by_id(tid)
        if tenant is None:
            yield _sse({"type": "error", "message": "Cliente no encontrado."})
            return

        async with _session_factory() as session:
            conv = (await session.execute(
                select(ChatConversation).where(
                    ChatConversation.id == body.conversation_id,
                    ChatConversation.tenant_id == tid,
                    ChatConversation.owner == owner,
                )
            )).scalar_one_or_none()
            if conv is None:
                yield _sse({"type": "error", "message": "Conversación no encontrada."})
                return

            if (conv.title or "").startswith("Nueva conversación"):
                conv.title = message[:60]
            conv.updated_at = datetime.now(timezone.utc)
            await session.commit()

            auth = AuthResult(allowed=True, user=None, role=None)
            full_permissions = frozenset(p.value for p in Permission)

            try:
                async for event in stream_chat(
                    message=message,
                    chat_id=conv.chat_id,
                    tenant=tenant,
                    session=session,
                    owner=owner,
                    source="web_chat",
                    forced_permissions=full_permissions,
                ):
                    yield _sse(event)
            except Exception as exc:
                logger.error("Error en stream de chat tenant=%s: %s", tid, exc)
                yield _sse({"type": "error", "message": "Ocurrió un error procesando la solicitud."})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
