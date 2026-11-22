"""Tests de la política de acceso a fuentes/tablas por rol."""
from __future__ import annotations

import pytest

from mind.agent.tools.registry import (
    PermissionDeniedError,
    get_allowed_tool_schemas,
)
from mind.auth.data_policy import (
    SourcePolicy,
    validate_tool_call,
)


def _commercial_policy() -> SourcePolicy:
    return SourcePolicy(
        restricted=True,
        allowed=frozenset({
            "knowledge",
            "ofima:clientes",
            "ofima:espclientes",
            "ofima:mtmercia",
            "ofima:mtseries",
            "ofima:mvprecio",
            "ofima:mvtrade",
            "ofima:v_clientes_fac",
            "ofima:ventas_bodega",
            "ofima:xmyct_tecnico_series",
        }),
    )


COMMERCIAL_PERMS = frozenset({"READ_SALES", "READ_KPI", "GENERATE_REPORT"})


def test_source_policy_deny_wins():
    policy = SourcePolicy(
        restricted=True,
        allowed=frozenset({"ofima:mvtrade", "ofima:vcxp"}),
        denied=frozenset({"ofima:vcxp"}),
    )
    assert policy.allows("ofima:mvtrade")
    assert not policy.allows("ofima:vcxp")


def test_source_policy_group_allows_children():
    policy = SourcePolicy(restricted=True, allowed=frozenset({"external_db"}))
    assert policy.allows("external_db")
    assert policy.allows("external_db:ventas")


def test_commercial_tools_exclude_finance_pii_and_external():
    tools = get_allowed_tool_schemas(COMMERCIAL_PERMS, _commercial_policy())
    names = {t["function"]["name"] for t in tools}
    assert "consultar_ventas" in names
    assert "consultar_indicadores" in names
    assert "consultar_finanzas" not in names
    assert "consultar_cxp" not in names
    assert "cliente_completo" not in names
    assert "ejecutar_consulta" not in names
    assert "consultar_alegra" not in names
    report = next(t for t in tools if t["function"]["name"] == "generar_informe")
    assert set(report["function"]["parameters"]["properties"]["tipo"]["enum"]) == {
        "ventas", "indicadores",
    }


def test_commercial_cannot_generate_finance_report():
    with pytest.raises(PermissionDeniedError):
        validate_tool_call(
            "generar_informe",
            {"tipo": "finanzas", "formato": "pdf"},
            COMMERCIAL_PERMS,
            _commercial_policy(),
        )


def test_commercial_can_generate_sales_report():
    validate_tool_call(
        "generar_informe",
        {"tipo": "ventas", "formato": "pdf"},
        COMMERCIAL_PERMS,
        _commercial_policy(),
    )


def test_commercial_sql_cannot_read_finance_table():
    with pytest.raises(PermissionDeniedError):
        validate_tool_call(
            "ejecutar_consulta",
            {"sql": "select * from vcxp"},
            COMMERCIAL_PERMS,
            _commercial_policy(),
        )


def test_cte_alias_is_not_treated_as_table():
    validate_tool_call(
        "ejecutar_consulta",
        {"sql": "WITH ventas AS (SELECT * FROM mvtrade) SELECT count(*) FROM ventas"},
        frozenset({"READ_EXTERNAL_DB"}),
        SourcePolicy(restricted=True, allowed=frozenset({"external_db"})),
    )


def test_system_schema_always_blocked():
    perms = frozenset({"READ_EXTERNAL_DB"})
    policy = SourcePolicy(restricted=True, allowed=frozenset({"external_db"}))
    with pytest.raises(PermissionDeniedError):
        validate_tool_call(
            "ejecutar_consulta",
            {"sql": "select * from pg_catalog.pg_user"},
            perms,
            policy,
        )


def test_unrestricted_policy_preserves_legacy_access():
    names = {
        t["function"]["name"]
        for t in get_allowed_tool_schemas(COMMERCIAL_PERMS, SourcePolicy())
    }
    assert "consultar_ventas" in names
    assert "consultar_indicadores" in names
    assert "cliente_completo" not in names  # falta READ_CUSTOMER_PII


@pytest.mark.asyncio
async def test_indicators_hide_finance_without_permission(monkeypatch):
    from mind.agent.tools import data_tools
    from mind.auth.context import set_current_permissions
    import mind.data.connectors as connectors

    monkeypatch.setattr(connectors, "get_sales_summary", lambda *a, **k: [
        {"total_ventas": 1000.0, "total_costo": 600.0, "num_transacciones": 3}
    ])
    monkeypatch.setattr(connectors, "get_cuentas_por_pagar", lambda *a, **k: [
        {"deuda": 500.0}
    ])

    set_current_permissions({"READ_KPI"})
    result = await data_tools.consultar_indicadores()
    labels = {i["indicador"] for i in result["indicadores"]}
    assert "Ventas Año Actual" in labels
    assert "Cuentas por Pagar" not in labels
    assert "Margen Bruto" not in labels

    set_current_permissions({"READ_KPI", "READ_FINANCE"})
    result = await data_tools.consultar_indicadores()
    labels = {i["indicador"] for i in result["indicadores"]}
    assert "Cuentas por Pagar" in labels
    assert "Margen Bruto" in labels


@pytest.mark.asyncio
async def test_sales_hide_cost_without_finance(monkeypatch):
    from mind.agent.tools import data_tools
    from mind.auth.context import set_current_permissions
    import mind.data.connectors as connectors

    monkeypatch.setattr(connectors, "get_sales_summary", lambda *a, **k: [
        {
            "periodo": "2026-01-01", "num_transacciones": 2,
            "total_ventas": 1000.0, "total_costo": 600.0,
            "utilidad_bruta": 400.0, "promedio_venta": 500.0,
        }
    ])
    monkeypatch.setattr(connectors, "get_sales", lambda *a, **k: [
        {"nrodcto": "1", "vlrventa": 1000.0, "costo": 600.0}
    ])

    set_current_permissions({"READ_SALES"})
    summary = await data_tools.consultar_ventas("2026-01-01", "2026-01-31")
    row = summary["resumen_mensual"][0]
    assert "total_costo" not in row
    assert "utilidad_bruta" not in row
    assert "total_ventas" in row

    detail = await data_tools.consultar_ventas_detalle("2026-01-01", "2026-01-31")
    assert "costo" not in detail["datos"][0]
    assert "vlrventa" in detail["datos"][0]

    set_current_permissions({"READ_SALES", "READ_FINANCE"})
    summary = await data_tools.consultar_ventas("2026-01-01", "2026-01-31")
    assert "total_costo" in summary["resumen_mensual"][0]
