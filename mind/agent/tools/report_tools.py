"""
Herramienta de generación de informes para el agente Mind.
Requisitos: 6.1 - 6.9
"""
from __future__ import annotations

from typing import Any

from mind.reports.generator import ReportGenerationError, generate_report as _gen


async def generar_informe(
    tipo: str,
    formato: str,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
) -> dict[str, Any]:
    """
    Genera un informe PDF o Excel y retorna la ruta del archivo temporal.

    El Orchestrator es responsable de enviar el archivo y eliminarlo tras el envío.
    Requisitos: 6.1, 6.2, 6.3, 6.6, 6.8
    """
    from mind.config import settings
    from mind.agent.tools.data_tools import (
        consultar_ventas,
        consultar_indicadores,
        consultar_finanzas,
        validate_date_params,
    )

    formato = formato.lower()
    if formato not in ("pdf", "excel"):
        return {"error": True, "mensaje": f"Formato no soportado: {formato!r}. Use 'pdf' o 'excel'."}

    # Obtener datos según tipo
    if tipo == "ventas":
        if not fecha_inicio or not fecha_fin:
            return {"error": True, "mensaje": "Se requieren fecha_inicio y fecha_fin para el informe de ventas."}
        v = validate_date_params(fecha_inicio, fecha_fin)
        if not v.is_valid:
            return {"error": True, "campo": v.error_field, "mensaje": v.error_message}
        result = await consultar_ventas(fecha_inicio, fecha_fin)
        titulo = "Informe de Ventas"
        periodo = f"{fecha_inicio} — {fecha_fin}"
        data = result.get("datos", [])

    elif tipo == "finanzas":
        if not fecha_inicio or not fecha_fin:
            return {"error": True, "mensaje": "Se requieren fecha_inicio y fecha_fin para el informe financiero."}
        v = validate_date_params(fecha_inicio, fecha_fin)
        if not v.is_valid:
            return {"error": True, "campo": v.error_field, "mensaje": v.error_message}
        result = await consultar_finanzas(fecha_inicio, fecha_fin)
        titulo = "Informe Financiero"
        periodo = f"{fecha_inicio} — {fecha_fin}"
        data = result.get("datos", [])

    elif tipo == "indicadores":
        result = await consultar_indicadores()
        titulo = "Informe de Indicadores"
        periodo = "Período actual"
        data = result.get("indicadores", [])

    else:
        return {"error": True, "mensaje": f"Tipo de informe no reconocido: {tipo!r}. Use 'ventas', 'finanzas' o 'indicadores'."}

    if not data:
        return {"error": True, "mensaje": "No hay datos disponibles para el período solicitado."}

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
