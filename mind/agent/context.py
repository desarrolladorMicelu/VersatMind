"""
Gestión del contexto de conversación para Mind by Versat.
Historial persistido en PostgreSQL por chat_id.
Requisitos: 4.1 - 4.7
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.db.models import ConversationMessage

MAX_CONTENT_CHARS = 32_000
DEFAULT_WINDOW = 20
MIN_RECENT_MESSAGES = 5  # siempre conservar los últimos 5


@dataclass
class Message:
    """Representa un mensaje en el historial de conversación."""
    role: str  # 'user' | 'assistant' | 'tool'
    content: str
    tool_name: str | None = None
    tool_call_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_openai_dict(self) -> dict[str, Any]:
        """Convierte a formato de mensaje de OpenAI."""
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.role == "tool" and self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class PromptContext:
    """Resultado de build_prompt."""
    messages: list[Message]


def _count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Aproximación de tokens: ~4 caracteres por token para español/inglés."""
    return len(text) // 4


def _total_tokens(messages: list[Message]) -> int:
    return sum(_count_tokens(m.content) for m in messages)


def truncate_to_token_limit(
    messages: list[Message],
    max_tokens: int,
) -> list[Message]:
    """
    Elimina mensajes más antiguos hasta estar dentro del límite de tokens.
    Siempre conserva los MIN_RECENT_MESSAGES (5) mensajes más recientes.
    Propiedad 12 — Valida: Requisito 4.3
    """
    if _total_tokens(messages) <= max_tokens:
        return messages

    recent = messages[-MIN_RECENT_MESSAGES:]
    older = messages[:-MIN_RECENT_MESSAGES]

    # Eliminar uno a uno desde el más antiguo hasta caber en el límite
    while older and _total_tokens(older + recent) > max_tokens:
        older.pop(0)

    return older + recent


def build_prompt(history: list[Message], n: int) -> PromptContext:
    """
    Construye el contexto del prompt con los últimos n mensajes.
    Función pura — sin I/O — para facilitar testing.
    Propiedad 9 — Valida: Requisitos 3.1, 4.2
    """
    n = max(1, min(n, 100))  # clamp al rango válido
    selected = history[-n:] if len(history) > n else history
    return PromptContext(messages=list(selected))


async def load_history(
    chat_id: int,
    tenant_id: int,
    n: int,
    session: AsyncSession,
) -> list[Message]:
    """
    Carga los últimos n mensajes del chat_id+tenant_id desde PostgreSQL.
    """
    stmt = (
        select(ConversationMessage)
        .where(
            ConversationMessage.chat_id == chat_id,
            ConversationMessage.tenant_id == tenant_id,
        )
        .order_by(ConversationMessage.created_at.desc())
        .limit(n)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    # Invertir para orden cronológico (más antiguo primero)
    return [
        Message(
            role=row.role,
            content=row.content,
            tool_name=row.tool_name,
            tool_call_id=row.tool_call_id,
            created_at=row.created_at,
        )
        for row in reversed(rows)
        if row.role in ("user", "assistant")
    ]


async def append_messages(
    chat_id: int,
    tenant_id: int,
    messages: list[Message],
    session: AsyncSession,
) -> None:
    """Persiste nuevos mensajes. Trunca content a MAX_CONTENT_CHARS."""
    for msg in messages:
        content = msg.content[:MAX_CONTENT_CHARS]
        row = ConversationMessage(
            chat_id=chat_id,
            tenant_id=tenant_id,
            role=msg.role,
            content=content,
            tool_name=msg.tool_name,
            tool_call_id=msg.tool_call_id,
        )
        session.add(row)
    await session.flush()


async def clear_history(
    chat_id: int,
    session: AsyncSession,
) -> None:
    """
    Elimina todo el historial del chat_id.
    Requisito: 4.6
    """
    stmt = delete(ConversationMessage).where(
        ConversationMessage.chat_id == chat_id
    )
    await session.execute(stmt)
    await session.flush()
