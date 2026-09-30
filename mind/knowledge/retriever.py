"""
Recuperación de la base de conocimiento por cliente.

Estrategia simple y sin dependencias externas:
  - Si el cliente tiene poca información (cabe en el presupuesto de caracteres),
    se inyecta completa.
  - Si tiene mucha, se priorizan las entradas con mayor coincidencia de
    palabras clave con la consulta.

Se usa tanto en el chat normal como en los prompts programados.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_WORD_RE = re.compile(r"[a-záéíóúñü0-9]{3,}", re.IGNORECASE)

DEFAULT_MAX_CHARS = 6000
STOPWORDS = {
    "que", "con", "los", "las", "del", "para", "por", "una", "uno", "unos",
    "unas", "como", "este", "esta", "esos", "esas", "pero", "mas", "más",
    "the", "and", "for", "with", "from", "this", "that",
}


def _tokens(text: str) -> set[str]:
    return {
        t.lower() for t in _WORD_RE.findall(text or "")
        if t.lower() not in STOPWORDS
    }


def _score(query_tokens: set[str], entry_tokens: set[str]) -> int:
    return len(query_tokens & entry_tokens)


def _format_entry(title: str, content: str) -> str:
    return f"### {title}\n{content.strip()}"


async def build_knowledge_context(
    session: AsyncSession,
    tenant_id: int,
    query: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str | None:
    """
    Retorna un bloque de texto con la información relevante del cliente,
    o None si el cliente no tiene información cargada.
    """
    from mind.db.models import KnowledgeEntry

    entries = (await session.execute(
        select(KnowledgeEntry)
        .where(KnowledgeEntry.tenant_id == tenant_id, KnowledgeEntry.is_active.is_(True))
        .order_by(KnowledgeEntry.updated_at.desc())
    )).scalars().all()

    if not entries:
        return None

    # Si toda la información cabe, se inyecta completa (más simple y fiable).
    total_chars = sum(len(e.content or "") + len(e.title or "") for e in entries)
    if total_chars <= max_chars:
        return "\n\n".join(
            _format_entry(e.title, e.content) for e in entries
        )

    # Si no cabe, se prioriza por coincidencia de palabras clave con la consulta.
    query_tokens = _tokens(query)
    scored = []
    for e in entries:
        tokens = _tokens(f"{e.title or ''} {e.tags or ''} {e.content or ''}")
        scored.append((_score(query_tokens, tokens), e))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    blocks: list[str] = []
    used = 0
    for score, e in scored:
        if score <= 0:
            continue
        block = _format_entry(e.title, e.content)
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining < 200:
                break
            block = block[:remaining]
        blocks.append(block)
        used += len(block)
        if used >= max_chars:
            break

    if not blocks:
        return None
    return "\n\n".join(blocks)
