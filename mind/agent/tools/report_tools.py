"""
Herramienta de generación de informes para el agente Mind.
Requisitos: 6.1 - 6.9
"""
from __future__ import annotations

from typing import Any

from mind.reports.generator import ReportGenerationError, generate_report as _gen

_HEADER_MAP = {
    "periodo": "Período",
    "num_transacciones": "Transacciones",
    "total_ventas": "Ventas",
    "total_costo": "Costo",
    "utilidad_bruta": "Utilidad bruta",
    "promedio_venta": "Promedio",
    "deuda": "Deuda",
    "valor": "Valor",
    "concepto": "Concepto",
    "indicador": "Indicador",
    "unidad": "Unidad",
    "proveedor": "Proveedor",
    "nombre": "Nombre",
    "documento": "Documento",
    "fecha": "Fecha",
    "nit": "NIT",
    "descripcion": "Descripción",
    "descripció": "Descripción",
    "tipo": "Tipo",
    "total": "Total",
}


def _headers(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    return [_HEADER_MAP.get(str(k).lower(), str(k).replace("_", " ").capitalize()) for k in rows[0].keys()]


def _section(title: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    keys = list(rows[0].keys())
    return {
        "title": title,
        "headers": _headers(rows),
        "rows": [[row.get(k, "") for k in keys] for row in rows],
        "summary": None,
    }


def _compact_sections(sections: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [s for s in sections if s is not None]


async def generar_informe(
    tipo: str,
    formato: str,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
) -> dict[str, Any]:
    """
    Genera un informe/tablero y retorna la ruta del archivo temporal o el
    reporte HTML persistido cuando se invoca desde el chat web.
    """
    from mind.config import settings
    from mind.agent.tools.data_tools import (
        consultar_ventas,
        consultar_indicadores,
        consultar_finanzas,
        validate_date_params,
    )

    formato = (formato or "pdf").lower()
    if formato not in ("pdf", "excel"):
        return {"error": True, "mensaje": f"Formato no soportado: {formato!r}. Use 'pdf' o 'excel'."}

    sections: list[dict[str, Any]] = []
    data: list[dict[str, Any]] = []

    if tipo == "ventas":
        if not fecha_inicio or not fecha_fin:
            return {"error": True, "mensaje": "Se requieren fecha_inicio y fecha_fin para el informe de ventas."}
        v = validate_date_params(fecha_inicio, fecha_fin)
        if not v.is_valid:
            return {"error": True, "campo": v.error_field, "mensaje": v.error_message}
        result = await consultar_ventas(fecha_inicio, fecha_fin)
        data = result.get("resumen_mensual") or result.get("datos") or []
        sections = _compact_sections([
            _section("Resumen mensual de ventas", data),
        ])
        titulo = "Informe de Ventas"
        periodo = f"{fecha_inicio} — {fecha_fin}"

    elif tipo == "finanzas":
        if not fecha_inicio or not fecha_fin:
            return {"error": True, "mensaje": "Se requieren fecha_inicio y fecha_fin para el informe financiero."}
        v = validate_date_params(fecha_inicio, fecha_fin)
        if not v.is_valid:
            return {"error": True, "campo": v.error_field, "mensaje": v.error_message}
        result = await consultar_finanzas(fecha_inicio, fecha_fin)
        resumen = result.get("resumen") or {}
        resumen_rows = [
            {"concepto": "Cuentas por pagar", "valor": resumen.get("total_cuentas_por_pagar", 0)},
            {"concepto": "Abonos recibidos", "valor": resumen.get("total_abonos_recibidos", 0)},
            {"concepto": "Movimientos de caja", "valor": resumen.get("total_movimientos_caja", 0)},
        ] if resumen else []
        sections = _compact_sections([
            _section("Resumen financiero", resumen_rows),
            _section("Cuentas por pagar", result.get("cuentas_por_pagar") or []),
            _section("Abonos", result.get("abonos") or []),
            _section("Caja", result.get("caja") or []),
        ])
        data = resumen_rows or result.get("cuentas_por_pagar") or []
        titulo = "Informe Financiero"
        periodo = f"{fecha_inicio} — {fecha_fin}"

    elif tipo == "indicadores":
        result = await consultar_indicadores()
        indicators = result.get("indicadores") or []
        data = indicators
        sections = _compact_sections([
            _section("Indicadores del período", indicators),
        ])
        titulo = "Informe de Indicadores"
        periodo = "Período actual"

    else:
        return {"error": True, "mensaje": f"Tipo de informe no reconocido: {tipo!r}. Use 'ventas', 'finanzas' o 'indicadores'."}

    if not sections and not data:
        return {"error": True, "mensaje": "No hay datos disponibles para el período solicitado."}

    from mind.tenants.context import get_tenant_or_none
    from mind.reports.service import create_web_report
    from mind.reports.context import get_report_context

    tenant = get_tenant_or_none()
    report_config = dict(getattr(tenant, "report_config", None) or {})
    if not report_config.get("company_name"):
        report_config["company_name"] = settings.CLIENT_NAME

    report = await create_web_report(
        sections=sections,
        title=titulo,
        period=periodo,
        report_type=titulo,
        config=report_config,
    )
    if report:
        return {
            "error": False,
            "report_id": report["id"],
            "report": report,
            "tipo": titulo,
            "formato": "html",
            "periodo": periodo,
            "num_registros": sum(len(s.get("rows") or []) for s in sections),
        }

    ctx = get_report_context()
    if ctx is not None and ctx.channel == "web":
        return {"error": True, "mensaje": "No se pudo guardar el informe en el chat."}

    try:
        file_path = await _gen(
            data=data,
            format=formato,
            title=titulo,
            period=periodo,
            client_name=settings.CLIENT_NAME,
            client_logo_path=settings.CLIENT_LOGO_PATH,
        )
        return {
            "error": False,
            "file_path": file_path,
            "tipo": titulo,
            "formato": formato,
            "periodo": periodo,
            "num_registros": len(data),
        }
    except ReportGenerationError as exc:
        return {"error": True, "mensaje": str(exc)}
