"""
Tests de las herramientas OFIMA adicionales (registro + ejecución con conector simulado).
"""
from __future__ import annotations

import pytest

from mind.agent.tools import ofima_tools, registry

NEW_TOOLS = [
    "catalogo_precios",
    "stock_celulares",
    "gangazos",
    "ventas_recientes",
    "inventario_bodega",
    "validar_imei",
    "historial_cliente",
    "buscar_cliente",
    "direccion_proveedor",
    "estado_sincronizacion_clientes",
    "inventario_activos",
    "cliente_completo",
    "factura_reciente_cliente",
    "medios_pago",
    "movimientos_contables",
]


class TestRegistration:

    def test_all_registered(self):
        for name in NEW_TOOLS:
            assert name in registry.TOOL_REGISTRY, f"falta {name}"
            assert registry.TOOL_REGISTRY[name].schema["name"] == name

    def test_schemas_are_valid(self):
        for name in NEW_TOOLS:
            schema = registry.TOOL_REGISTRY[name].schema
            assert schema["parameters"]["type"] == "object"
            assert "properties" in schema["parameters"]


class TestExecution:

    @pytest.mark.asyncio
    async def test_stock_celulares(self, monkeypatch):
        import mind.data.connectors as conn
        monkeypatch.setattr(conn, "get_stock_celulares", lambda creds=None: [{"codigo": "X", "cantidad": 3}])
        res = await ofima_tools.stock_celulares()
        assert res["error"] is False
        assert res["total_referencias"] == 1

    @pytest.mark.asyncio
    async def test_catalogo_precios_passes_args(self, monkeypatch):
        import mind.data.connectors as conn
        captured = {}

        def fake(filtro="", limite=200, creds=None):
            captured["filtro"] = filtro
            captured["limite"] = limite
            return [{"descripcio": "iPhone"}]

        monkeypatch.setattr(conn, "get_catalogo_precios", fake)
        res = await ofima_tools.catalogo_precios("iphone", 50)
        assert res["error"] is False
        assert captured == {"filtro": "iphone", "limite": 50}

    @pytest.mark.asyncio
    async def test_validar_imei_reports_found(self, monkeypatch):
        import mind.data.connectors as conn
        monkeypatch.setattr(conn, "get_imei", lambda imei, creds=None: [{"serie": imei, "bodega": "BM"}])
        res = await ofima_tools.validar_imei("12345")
        assert res["encontrado"] is True

    @pytest.mark.asyncio
    async def test_cliente_completo(self, monkeypatch):
        import mind.data.connectors as conn
        monkeypatch.setattr(conn, "get_cliente_completo", lambda nit, creds=None: [{"nit": nit, "nombre": "ANA"}])
        res = await ofima_tools.cliente_completo("123")
        assert res["encontrado"] is True

    @pytest.mark.asyncio
    async def test_movimientos_invalid_dates(self):
        res = await ofima_tools.movimientos_contables("no-es-fecha", "tampoco")
        assert res["error"] is True

    @pytest.mark.asyncio
    async def test_movimientos_ok(self, monkeypatch):
        import mind.data.connectors as conn

        def fake(start, end, limite=500, creds=None):
            return [{"dcto": "1", "tercero": "X"}]

        monkeypatch.setattr(conn, "get_movimientos_contables", fake)
        res = await ofima_tools.movimientos_contables("2026-09-01", "2026-10-01")
        assert res["error"] is False
        assert res["total_registros"] == 1

    @pytest.mark.asyncio
    async def test_error_is_captured(self, monkeypatch):
        import mind.data.connectors as conn

        def boom(creds=None):
            raise RuntimeError("sin conexión")

        monkeypatch.setattr(conn, "get_gangazos", boom)
        res = await ofima_tools.gangazos()
        assert res["error"] is True
        assert "sin conexión" in res["mensaje"]
