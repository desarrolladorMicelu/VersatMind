"""
Herramienta `generar_informe_contable`: genera un PDF personalizado
con los datos contables del cliente.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def generar_informe_contable(
    secciones: list[dict],
    periodo: str,
    titulo: str | None = None,
) -> dict:
    """
    Genera un informe contable PDF con las secciones proporcionadas.

    - `secciones`: lista de secciones, cada una con:
        - title: str — título de la sección
        - headers: list[str] — nombres de columnas
        - rows: list[list] — filas de datos
        - summary: str (opcional) — texto de resumen
    - `periodo`: período del informe (ej: 'Septiembre 2026')
    - `titulo`: título opcional (default: 'Informe Contable')
    """
    from mind.tenants.context import get_tenant_or_none
    from mind.reports.generator import generate_custom_report, ReportGenerationError
    from mind.reports.service import create_web_report

    tenant = get_tenant_or_none()
    report_config = getattr(tenant, "report_config", None) or {}

    if not secciones:
        return {"error": True, "mensaje": "No hay secciones para el informe."}

    # En el chat web se guarda un tablero HTML autocontenido. En Telegram se
    # mantiene el PDF existente de VT-51.
    report = await create_web_report(
        sections=secciones,
        title=titulo or "Informe",
        period=periodo,
        report_type="Informe",
        config=report_config,
    )
    if report:
        return {
            "error": False,
            "report_id": report["id"],
            "report": report,
            "filename": f"{titulo or 'Informe'}_{periodo}.html",
        }

    from mind.reports.context import get_report_context
    ctx = get_report_context()
    if ctx is not None and ctx.channel == "web":
        return {"error": True, "mensaje": "No se pudo guardar el informe en el chat."}

    try:
        file_path = await generate_custom_report(
            sections=secciones,
            report_config=report_config,
            period=periodo,
            title=titulo,
        )
        return {"error": False, "file_path": file_path, "filename": f"{titulo or 'Informe'}_{periodo}.pdf"}
    except ReportGenerationError as exc:
        return {"error": True, "mensaje": str(exc)}
    except Exception as exc:
        logger.warning("Error en generar_informe_contable tenant=%s: %s", getattr(tenant, "slug", "?"), exc)
        return {"error": True, "mensaje": f"Error generando informe: {exc}"}