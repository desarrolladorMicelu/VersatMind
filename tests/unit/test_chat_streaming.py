"""
Tests de la interfaz web de chat: helpers de streaming y formato SSE.
"""
from __future__ import annotations

from types import SimpleNamespace

from mind.agent.streaming import _filter_tools, tool_label
from mind.chat.routes import WEB_CHAT_BASE, _sse


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "parameters": {}}}


def _tenant(*, ofima=False, ext_db=False, sheets=False, alegra=False):
    return SimpleNamespace(
        sqlserver_host="host" if ofima else None,
        external_db={"x": 1} if ext_db else None,
        external_sheets={"x": 1} if sheets else None,
        external_alegra={"token": "t"} if alegra else None,
    )


class TestToolFilter:

    def test_excludes_unconfigured_integrations(self):
        tools = [_tool("consultar_ventas"), _tool("ejecutar_consulta"), _tool("consultar_alegra")]
        assert _filter_tools(tools, _tenant()) == []

    def test_keeps_external_db_when_configured(self):
        tools = [_tool("consultar_ventas"), _tool("ejecutar_consulta")]
        names = [t["function"]["name"] for t in _filter_tools(tools, _tenant(ext_db=True))]
        assert names == ["ejecutar_consulta"]

    def test_keeps_alegra_when_token_present(self):
        tools = [_tool("consultar_alegra")]
        names = [t["function"]["name"] for t in _filter_tools(tools, _tenant(alegra=True))]
        assert names == ["consultar_alegra"]

    def test_keeps_ofima_tools_when_configured(self):
        tools = [_tool("consultar_ventas"), _tool("crear_tarea_programada")]
        names = [t["function"]["name"] for t in _filter_tools(tools, _tenant(ofima=True))]
        assert names == ["consultar_ventas", "crear_tarea_programada"]


class TestToolLabel:

    def test_known_tool(self):
        assert tool_label("consultar_alegra") == "Consultando Alegra"

    def test_unknown_tool_falls_back_to_name(self):
        assert tool_label("desconocida") == "desconocida"


class TestSseFormat:

    def test_sse_line(self):
        out = _sse({"type": "delta", "text": "hola"})
        assert out.startswith("data: ")
        assert out.endswith("\n\n")
        assert '"type": "delta"' in out


class TestWebChatId:

    def test_ids_are_negative_and_unique(self):
        ids = {WEB_CHAT_BASE - i for i in range(1, 4)}
        assert len(ids) == 3
        assert all(i < 0 for i in ids)
