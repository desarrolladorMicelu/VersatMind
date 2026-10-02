"""
Generador de informes PDF y Excel para Mind by Versat.
Los informes PDF se generan desde una plantilla HTML/CSS (Jinja2 + WeasyPrint)
para poder visualizarla y personalizarla fácilmente.
"""
from __future__ import annotations

import asyncio
import base64
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


class ReportGenerationError(Exception):
    """Se lanza cuando falla la generación del informe."""


def _safe_footer(text: str) -> str:
    """Sanitiza el texto del pie de página para usarlo en content CSS."""
    return (
        text.replace("\\", "")
        .replace('"', "'")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _extra_css(config: dict) -> str:
    """CSS extra por tenant (campo template_style), opcional."""
    css = (config or {}).get("template_style") or ""
    if not css:
        return ""
    if "</style" in css.lower():
        return ""
    return css


def _logo_data_uri(logo_b64: str | None) -> str:
    """Convierte el logo base64 a data URI con el MIME detectado."""
    if not logo_b64:
        return ""
    try:
        data = base64.b64decode(logo_b64)
    except Exception:
        return ""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        mime = "image/gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{logo_b64}"


def _normalize_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normaliza secciones: valores a texto y None a cadena vacía."""
    result = []
    for sec in sections:
        headers = ["" if h is None else str(h) for h in (sec.get("headers") or [])]
        rows = []
        for row in sec.get("rows") or []:
            rows.append(["" if c is None else str(c) for c in row])
        result.append({
            "title": sec.get("title", ""),
            "headers": headers,
            "rows": rows,
            "summary": sec.get("summary") or "",
        })
    return result


def render_report_html(
    sections: list[dict[str, Any]],
    config: dict,
    period: str,
    title: str | None = None,
) -> str:
    """
    Renderiza la plantilla HTML del informe.

    Puede usarse para previsualizar el informe en el navegador
    sin generar el PDF.
    """
    config = config or {}
    company = config.get("company_name") or "Empresa"
    final_title = title or "Informe Contable"
    footer_left = _safe_footer(f"{company} | {final_title} | {period}")

    tpl = _env.get_template("informe_contable.html")
    return tpl.render(
        company=company,
        title=final_title,
        period=period,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
        logo=_logo_data_uri(config.get("company_logo")),
        footer_left=footer_left,
        extra_css=_extra_css(config),
        sections=_normalize_sections(sections or []),
    )


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
    - template_style: str | None (CSS extra opcional)
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


def _tmp_pdf_path(title: str, period: str) -> str:
    tmp_dir = tempfile.mkdtemp(prefix="mind_report_")
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
    return os.path.join(tmp_dir, f"{safe}_{period.replace(' ', '_')}.pdf")


def _generate_custom_pdf(
    sections: list[dict[str, Any]],
    config: dict,
    period: str,
    title: str | None,
) -> str:
    """Genera el PDF del informe desde la plantilla HTML con WeasyPrint."""
    from weasyprint import HTML

    html = render_report_html(sections, config, period, title)
    file_path = _tmp_pdf_path(title or "Informe Contable", period)
    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(file_path)
    return file_path


def _generate_pdf(
    data: list[dict[str, Any]],
    title: str,
    period: str,
    client_name: str,
    client_logo_path: str | None,
) -> str:
    """Genera un PDF simple (una sección) a partir de lista de dicts."""
    config: dict = {"company_name": client_name}
    if client_logo_path and os.path.exists(client_logo_path):
        try:
            with open(client_logo_path, "rb") as f:
                config["company_logo"] = base64.b64encode(f.read()).decode("ascii")
        except Exception:
            pass

    headers = list(data[0].keys())
    rows = [[str(row.get(h, "")) for h in headers] for row in data]
    sections = [{"title": title, "headers": headers, "rows": rows, "summary": None}]
    return _generate_custom_pdf(sections, config, period, title)


def _clean_cell(value: Any) -> Any:
    """Limpia valores para Excel (openpyxl rechaza caracteres de control XML)."""
    if isinstance(value, str):
        return "".join(
            ch for ch in value if ch in "\t\n\r" or ord(ch) >= 32
        )
    return value


def _generate_excel(
    data: list[dict[str, Any]],
    title: str,
    period: str,
    client_name: str,
) -> str:
    """Genera un Excel simple a partir de lista de dicts."""
    from openpyxl import Workbook

    tmp_dir = tempfile.mkdtemp(prefix="mind_report_")
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
    file_path = os.path.join(tmp_dir, f"{safe}_{period.replace(' ', '_')}.xlsx")

    wb = Workbook()
    ws = wb.active
    ws["A1"] = client_name
    ws["A2"] = title
    ws["A3"] = f"Período: {period}"

    headers = list(data[0].keys())
    for ci, header in enumerate(headers, start=1):
        ws.cell(row=5, column=ci, value=_clean_cell(header))
    for ri, row in enumerate(data, start=6):
        for ci, header in enumerate(headers, start=1):
            ws.cell(row=ri, column=ci, value=_clean_cell(row.get(header, "")))

    wb.save(file_path)
    return file_path
