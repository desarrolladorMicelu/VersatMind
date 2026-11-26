"""Tests del conector JSON y visibilidad de tools."""
from mind.auth.data_policy import SourcePolicy, validate_tool_call, tool_source_allowed
from mind.agent.tools.registry import PermissionDeniedError, get_allowed_tool_schemas
from mind.data.json_source import query_historial, query_precios, summary_historial, summary_precios


PRECIOS = [
    {
        "nombre": "Iphone 16 128Gb", "codigo": "103747082", "codigo_ofim": "16128FN",
        "total_vendedores": 2,
        "posicion_1": {"vendedor": "mundomovil", "precio": "$3.098.898", "precio_numerico": 3098898.0},
        "micelu": {"existe": False, "posicion": None, "precio": None, "precio_numerico": None,
                    "diferencia_vs_posicion1": None, "diferencia_porcentaje": None},
    },
    {
        "nombre": "Iphone 13 Pro Reacondicionado", "codigo": "103495334", "codigo_ofim": "13PRO128",
        "total_vendedores": 4,
        "posicion_1": {"vendedor": "refurbi", "precio": "$1.628.641", "precio_numerico": 1628641.0},
        "micelu": {"existe": True, "posicion": 4, "precio": "$1.629.566", "precio_numerico": 1629566.0,
                    "diferencia_vs_posicion1": 925.0, "diferencia_porcentaje": 0.06},
    },
]
HISTORIAL = [
    {"producto": "Iphone 13 Pro", "codigo": "103495334", "fecha": "2026-11-18T13:30:22",
     "tipo_cambio": "Producto nuevo con Micelu"},
    {"producto": "Iphone 13 Pro", "codigo": "103495334", "fecha": "2026-11-20T13:30:22",
     "tipo_cambio": "Cambio de posición Micelu"},
]


def test_query_precios_and_summary():
    result = query_precios(PRECIOS, solo_con_micelu=True)
    assert result["total"] == 1
    assert result["items"][0]["codigo"] == "103495334"
    summary = summary_precios(PRECIOS)
    assert summary["total_productos"] == 2
    assert summary["con_micelu"] == 1


def test_query_historial_and_summary():
    result = query_historial(HISTORIAL, tipo_cambio="posición", limit=1)
    assert result["total"] == 1
    assert result["items"][0]["codigo"] == "103495334"
    summary = summary_historial(HISTORIAL)
    assert summary["total_cambios"] == 2
    assert summary["productos_distintos"] == 1


def test_json_tools_require_source_policy():
    perms = frozenset({"READ_JSON_DATA"})
    policy = SourcePolicy(restricted=True, allowed=frozenset({"json:precios"}))
    names = {t["function"]["name"] for t in get_allowed_tool_schemas(perms, policy)}
    assert "consultar_precios_exito" in names
    assert "consultar_historial_exito" not in names
    assert tool_source_allowed("consultar_precios_exito", perms, policy)
    assert not tool_source_allowed("consultar_historial_exito", perms, policy)
    with_error = False
    try:
        validate_tool_call("consultar_historial_exito", {}, perms, policy)
    except PermissionDeniedError:
        with_error = True
    assert with_error
