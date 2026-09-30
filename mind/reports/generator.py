"""
Generador de informes PDF y Excel para Mind by Versat.
Incluye branding del cliente configurable e informes contables
personalizados por secciones.
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


class ReportGenerationError(Exception):
    """Se lanza cuando falla la generación del informe."""


async def generate_report(
    data: list[dict[str, Any]],
    format: Literal["pdf", "excel"],
    title: str,
    period: str,
    client_name: str = "Versat",
    client_logo_path: str | None = None,
) -> str:
    """Genera un informe PDF o Excel y retorna la ruta absoluta del archivo temporal."""
    if not data:
        raise ReportGenerationError("No hay datos para generar el informe.")

    try:
        async with asyncio.timeout(60):
            if format == "pdf":
                return await asyncio.to_thread(
                    _generate_pdf, data, title, period, client_name, client_logo_path
                )
            elif format == "excel":
                return await asyncio.to_thread(
                    _generate_excel, data, title, period, client_name
                )
            raise ReportGenerationError(f"Formato no soportado: {format!r}")
    except asyncio.TimeoutError:
        raise ReportGenerationError("Timeout: la generación del informe excedió 60 segundos.")
    except ReportGenerationError:
        raise
    except Exception as exc:
        raise ReportGenerationError(f"Error al generar informe: {exc}") from exc


async def generate_custom_report(
    sections: list[dict[str, Any]],
    report_config: dict,
    period: str,
    title: str | None = None,
) -> str:
    """
    Genera un informe contable personalizado con secciones dinámicas.

    Cada section tiene:
    - title: str — título de la sección
    - headers: list[str] — nombres de columnas
    - rows: list[list[str]] — filas de datos
    - summary: str | None — texto de resumen opcional

    report_config tiene:
    - company_name: str
    - company_logo: str (base64)
    - sections: list[str] (habilitadas)
    - additional_instructions: str | None
    """
    if not sections:
        raise ReportGenerationError("No hay secciones para el informe.")

    try:
        async with asyncio.timeout(60):
            return await asyncio.to_thread(
                _generate_custom_pdf, sections, report_config, period, title
            )
    except asyncio.TimeoutError:
        raise ReportGenerationError("Timeout generando el informe (60 s).")
    except ReportGenerationError:
        raise
    except Exception as exc:
        raise ReportGenerationError(f"Error al generar informe: {exc}") from exc


def _generate_custom_pdf(
    sections: list[dict[str, Any]],
    config: dict,
    period: str,
    title: str | None,
) -> str:
    """Genera PDF con reportlab usando secciones dinámicas."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    company = (config or {}).get("company_name", "Empresa")
    logo_b64 = (config or {}).get("company_logo", "")
    final_title = title or "Informe Contable"
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    tmp_dir = tempfile.mkdtemp(prefix="mind_report_")
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in final_title)
    file_path = os.path.join(tmp_dir, f"{safe}_{period.replace(' ', '_')}.pdf")

    doc = SimpleDocTemplate(
        file_path, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceAfter=4,
                        textColor=colors.HexColor("#1a1a2e"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceAfter=6,
                        spaceBefore=8, textColor=colors.HexColor("#1a1a2e"))
    meta = ParagraphStyle("meta", parent=styles["Normal"], fontSize=8,
                          textColor=colors.grey)
    summary_style = ParagraphStyle("summary", parent=styles["Normal"],
                                   fontSize=9, textColor=colors.HexColor("#333333"),
                                   spaceAfter=6)

    elements = []

    # Logo
    if logo_b64:
        try:
            logo_bytes = base64.b64decode(logo_b64)
            logo_fp = io.BytesIO(logo_bytes)
            img = Image(logo_fp, width=4*cm, height=2*cm)
            elements.append(img)
        except Exception:
            pass

    # Encabezado
    elements.append(Paragraph(f"{company}", h1))
    elements.append(Paragraph(f"{final_title}", styles["Heading2"]))
    elements.append(Paragraph(f"Período: {period} | Generado: {now}", meta))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
    elements.append(Spacer(1, 0.5*cm))

    # Secciones
    for sec in sections:
        sec_title = sec.get("title", "")
        headers = sec.get("headers", [])
        rows = sec.get("rows", [])
        summary = sec.get("summary")

        if not headers and not rows:
            continue

        elements.append(Paragraph(sec_title, h2))

        table_data = [headers] + rows
        col_count = max(len(headers), 1)
        available = A4[0] - 4*cm
        col_w = min(available / col_count, 5*cm)

        tbl = Table(table_data, colWidths=[col_w]*col_count, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(tbl)

        if summary:
            elements.append(Paragraph(summary, summary_style))
        elements.append(Spacer(1, 0.3*cm))

    # Pie
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(2*cm, 1*cm, f"{company} | {final_title} | {period}")
        canvas.drawRightString(A4[0]-2*cm, 1*cm, f"Página {doc.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    return file_path
