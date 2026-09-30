"""
Tests de la recuperación de la base de conocimiento por cliente.
Valida mind/knowledge/retriever.py con una sesión falsa (sin BD).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from mind.knowledge.retriever import (
    _score,
    _tokens,
    build_knowledge_context,
)


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)


class _FakeSession:
    def __init__(self, items):
        self._items = items

    async def execute(self, _stmt):
        return _FakeResult(self._items)


def _entry(title, content, tags=""):
    return SimpleNamespace(title=title, content=content, tags=tags)


class TestTokenHelpers:

    def test_tokens_extracts_words(self):
        assert "ventas" in _tokens("Ventas del mes")

    def test_stopwords_removed(self):
        toks = _tokens("ventas de la tienda para el mes")
        assert "para" not in toks
        assert "ventas" in toks

    def test_score_overlap(self):
        assert _score({"ventas", "mes"}, {"ventas", "mes", "metas"}) == 2


class TestBuildKnowledgeContext:

    @pytest.mark.asyncio
    async def test_no_entries_returns_none(self):
        session = _FakeSession([])
        assert await build_knowledge_context(session, 1, "ventas") is None

    @pytest.mark.asyncio
    async def test_small_kb_returns_all(self):
        entries = [
            _entry("Política de precios", "El precio mínimo es X"),
            _entry("Metas", "Meta mensual 100M"),
        ]
        session = _FakeSession(entries)
        out = await build_knowledge_context(session, 1, "cualquier cosa")
        assert out is not None
        assert "Política de precios" in out
        assert "Metas" in out

    @pytest.mark.asyncio
    async def test_large_kb_filters_by_relevance(self):
        entries = [
            _entry("Metas de ventas", "ventas meta asesor cumplimiento", "ventas metas"),
            _entry("Inventario bodega", "stock productos agotados", "stock inventario"),
        ]
        # Forzar la rama de recuperación con un presupuesto menor al total
        session = _FakeSession(entries)
        out = await build_knowledge_context(session, 1, "stock agotado", max_chars=60)
        assert out is not None
        assert "Inventario bodega" in out
