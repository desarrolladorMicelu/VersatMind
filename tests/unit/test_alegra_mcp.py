"""
Tests unitarios para el módulo de Alegra MCP.
Cubre: _basic_token, _is_readonly, filtrado de tools.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mind.data.alegra.alegra_mcp import (
    AlegraError,
    _basic_token,
    _is_readonly,
    discover_tools,
    READONLY_GROUPS,
)


class TestBasicToken:
    def test_creates_base64_token(self):
        token = _basic_token("user@test.com", "abc123")
        assert token == "dXNlckB0ZXN0LmNvbTphYmMxMjM="

    def test_different_credentials(self):
        token = _basic_token("a@b.co", "xyz")
        assert token == "YUBiLmNvOnh5eg=="


class TestIsReadonly:
    def test_list_tool_is_readonly(self):
        assert _is_readonly("contacts__list_contacts") is True

    def test_get_tool_is_readonly(self):
        assert _is_readonly("items__get_item") is True

    def test_create_tool_is_not_readonly(self):
        assert _is_readonly("items__create_item") is False

    def test_update_tool_is_not_readonly(self):
        assert _is_readonly("contacts__update_contact") is False

    def test_delete_tool_is_not_readonly(self):
        assert _is_readonly("bills__delete_bill") is False

    def test_void_tool_is_not_readonly(self):
        assert _is_readonly("purchase-orders__void-purchase-order") is False

    def test_email_tool_is_not_readonly(self):
        assert _is_readonly("purchase-orders__email-purchase-order") is False

    def test_upload_tool_is_not_readonly(self):
        assert _is_readonly("bills__upload_bill_attachment") is False

    def test_add_tool_is_not_readonly(self):
        assert _is_readonly("bills__add_bill_comments") is False

    def test_apply_tool_is_not_readonly(self):
        assert _is_readonly("bills__apply_bill_advances") is False


class TestDiscoverTools:
    @pytest.mark.asyncio
    async def test_empty_config_raises(self):
        with pytest.raises(AlegraError, match="Faltan email o token"):
            await discover_tools({})

    @pytest.mark.asyncio
    async def test_no_tools_found_raises(self):
        mock_tool_list = MagicMock()
        mock_tool_list.tools = []

        with patch("mcp.Client") as mock_cls:
            mock_ctx = AsyncMock()
            mock_instance = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_instance
            mock_cls.return_value = mock_ctx
            mock_instance.list_tools = AsyncMock(return_value=mock_tool_list)

            with pytest.raises(AlegraError):
                await discover_tools({"email": "a@b.com", "token": "xyz"})

    @pytest.mark.asyncio
    async def test_discover_returns_only_readonly(self):
        def _tool(name, desc=""):
            t = MagicMock()
            t.name = name
            t.description = desc
            t.input_schema = {}
            return t

        mock_tool_list = MagicMock()
        mock_tool_list.tools = [
            _tool("contacts__list_contacts", "List contacts"),
            _tool("contacts__create_contact", "Create contact"),
            _tool("items__get_item", "Get item"),
            _tool("items__delete_item", "Delete item"),
            _tool("invoices__list_invoices", "List invoices"),
        ]

        with patch("mcp.Client") as mock_cls:
            mock_ctx = AsyncMock()
            mock_instance = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_instance
            mock_cls.return_value = mock_ctx
            mock_instance.list_tools = AsyncMock(return_value=mock_tool_list)

            result = await discover_tools({"email": "a@b.com", "token": "xyz"})

            names = [t["name"] for t in result]
            assert "contacts__list_contacts" in names
            assert "items__get_item" in names
            assert "invoices__list_invoices" in names
            assert "contacts__create_contact" not in names
            assert "items__delete_item" not in names


class TestReadonlyGroups:
    def test_contacts_in_readonly(self):
        assert "contacts" in READONLY_GROUPS

    def test_items_in_readonly(self):
        assert "items" in READONLY_GROUPS

    def test_invoices_in_readonly(self):
        assert "invoices" in READONLY_GROUPS

    def test_gastos_not_in_readonly(self):
        assert "gastos" not in READONLY_GROUPS

    def test_ingresos_not_in_readonly(self):
        assert "ingresos" not in READONLY_GROUPS