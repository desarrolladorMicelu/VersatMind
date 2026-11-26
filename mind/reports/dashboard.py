"""
Tableros HTML autocontenidos para el chat web.

Reutiliza la normalización de secciones del generador de informes y agrega
KPIs y gráficos SVG generados en el servidor (sin JavaScript), para que el
HTML se pueda mostrar en un iframe con sandbox.
"""
from __future__ import annotations

import html
import json
import math
import re
from datetime import datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from mind.reports.generator import (
    TEMPLATES_DIR,
    _logo_data_uri,
    _normalize_sections,
    _safe_footer,
)

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

_CURRENCY_HINTS = (
    "valor", "venta", "costo", "deuda", "monto", "total", "saldo", "precio",
    "abono", "caja", "utilidad", "ingreso", "egreso", "ticket", "cop", "usd",
)
_PERCENT_HINTS = ("margen", "porcentaje", "%", "participacion", "participación")
_CHART_COLORS = [
    "#0a4f46", "#2f7d73", "#6aa79e", "#a8c9c2", "#d5e4e0",
]


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = re.sub(r"[^0-9,.\-]", "", text)
    if not text or text in {"-", ".", ","}:
        return None
    try:
        if "," in text and "." in text:
            # Formato colombiano: 1.234.567,89
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            if text.count(",") == 1 and len(text.split(",")[-1]) in (1, 2):
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
        elif text.count(".") > 1:
            # Separador de miles: 125.000.000
            text = text.replace(".", "")
        elif text.count(".") == 1:
            left, right = text.split(".", 1)
            if len(right) == 3 and len(left) <= 3:
                # 125.000 o 1.037 se interpretan como miles.
                text = left + right
        number = float(text)
        return -number if negative else number
    except ValueError:
        return None


def _format_number(value: float, header: str = "") -> str:
    lower = header.lower()
    if any(h in lower for h in _PERCENT_HINTS):
        return f"{value:,.1f}%".replace(",", ".")
    if any(h in lower for h in _CURRENCY_HINTS):
        return f"${value:,.0f}".replace(",", ".")
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.1f}M".replace(",", ".")
    if abs(value) >= 10_000:
        return f"{value:,.0f}".replace(",", ".")
    return f"{value:,.2f}".replace(",", ".").rstrip("0").rstrip(".")


def _numeric_columns(section: dict[str, Any]) -> list[int]:
    rows = section.get("rows") or []
    headers = section.get("headers") or []
    result: list[int] = []
    for idx in range(len(headers)):
        values = [row[idx] for row in rows if idx < len(row)]
        parsed = [_parse_number(v) for v in values]
        numeric = [v for v in parsed if v is not None]
        if numeric and len(numeric) >= max(1, math.ceil(len(values) * 0.6)):
            result.append(idx)
    return result


def _label_column(section: dict[str, Any], numeric_cols: list[int]) -> int | None:
    headers = section.get("headers") or []
    for idx in range(len(headers)):
        if idx not in numeric_cols:
            return idx
    return 0 if headers else None


def _short(text: Any, limit: int = 26) -> str:
    value = str(text or "")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _svg_bar(section: dict[str, Any]) -> dict[str, Any] | None:
    rows = section.get("rows") or []
    headers = section.get("headers") or []
    numeric = _numeric_columns(section)
    if not rows or not numeric:
        return None
    label_idx = _label_column(section, numeric)
    if label_idx is None:
        return None
    value_idx = numeric[0]
    points = []
    for row in rows:
        if label_idx >= len(row) or value_idx >= len(row):
            continue
        value = _parse_number(row[value_idx])
        if value is None:
            continue
        points.append((str(row[label_idx]), value))
    if not points:
        return None
    points.sort(key=lambda p: abs(p[1]), reverse=True)
    points = points[:8]

    width, height = 680, 300
    left, right, top, bottom = 150, 80, 24, 20
    chart_w = width - left - right
    row_h = max(24, (height - top - bottom) / max(len(points), 1))
    max_value = max(abs(v) for _, v in points) or 1
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(section.get("title", "Gráfico"))}">']
    for i, (label, value) in enumerate(points):
        y = top + i * row_h
        bar_w = max(2, abs(value) / max_value * chart_w)
        color = _CHART_COLORS[0] if value >= 0 else "#a61b14"
        parts.append(
            f'<text x="{left - 10}" y="{y + row_h * 0.64}" text-anchor="end" '
            f'font-size="12" fill="#5f6267">{html.escape(_short(label))}</text>'
        )
        parts.append(
            f'<rect x="{left}" y="{y + 5}" width="{bar_w:.1f}" height="{max(10, row_h - 12)}" '
            f'rx="4" fill="{color}" opacity="0.92"/>'
        )
        parts.append(
            f'<text x="{left + bar_w + 7}" y="{y + row_h * 0.64}" '
            f'font-size="11" fill="#202124">{html.escape(_format_number(value, headers[value_idx]))}</text>'
        )
    parts.append("</svg>")
    return {
        "title": section.get("title") or "Distribución",
        "subtitle": f"Top {len(points)} · {headers[value_idx]}",
        "svg": "".join(parts),
        "data": {
            "labels": [label for label, _ in points],
            "values": [value for _, value in points],
            "series": headers[value_idx],
            "type": "bar",
        },
    }


def _svg_donut(section: dict[str, Any]) -> dict[str, Any] | None:
    rows = section.get("rows") or []
    headers = section.get("headers") or []
    numeric = _numeric_columns(section)
    if not rows or not numeric:
        return None
    label_idx = _label_column(section, numeric)
    if label_idx is None:
        return None
    value_idx = numeric[0]
    points = []
    for row in rows:
        if label_idx >= len(row) or value_idx >= len(row):
            continue
        value = _parse_number(row[value_idx])
        if value is None or value <= 0:
            continue
        points.append((str(row[label_idx]), value))
    if not points:
        return None
    points.sort(key=lambda p: p[1], reverse=True)
    points = points[:5]
    total = sum(v for _, v in points) or 1

    width, height = 680, 300
    cx, cy, radius = 165, 150, 92
    circumference = 2 * math.pi * radius
    offset = 0.0
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(section.get("title", "Gráfico"))}">']
    for i, (label, value) in enumerate(points):
        fraction = value / total
        length = fraction * circumference
        color = _CHART_COLORS[i % len(_CHART_COLORS)]
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{color}" '
            f'stroke-width="26" stroke-dasharray="{length:.2f} {circumference - length:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})"/>'
        )
        offset += length
    parts.append(f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="12" fill="#5f6267">Total</text>')
    parts.append(f'<text x="{cx}" y="{cy + 20}" text-anchor="middle" font-size="20" font-weight="700" fill="#202124">{html.escape(_format_number(total, headers[value_idx]))}</text>')
    for i, (label, value) in enumerate(points):
        y = 70 + i * 38
        color = _CHART_COLORS[i % len(_CHART_COLORS)]
        parts.append(f'<circle cx="355" cy="{y}" r="6" fill="{color}"/>')
        parts.append(f'<text x="370" y="{y + 4}" font-size="12" fill="#202124">{html.escape(_short(label, 24))}</text>')
        parts.append(f'<text x="640" y="{y + 4}" text-anchor="end" font-size="12" fill="#5f6267">{value / total * 100:.1f}%</text>')
    parts.append("</svg>")
    return {
        "title": f"Participación por {headers[label_idx]}",
        "subtitle": f"{section.get('title') or 'Distribución'} · Top {len(points)}",
        "svg": "".join(parts),
        "data": {
            "labels": [label for label, _ in points],
            "values": [value for _, value in points],
            "series": headers[value_idx],
            "type": "donut",
        },
    }


def _build_kpis(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kpis: list[dict[str, Any]] = []
    for section_index, section in enumerate(sections):
        numeric = _numeric_columns(section)
        for idx in numeric:
            values = [
                _parse_number(row[idx])
                for row in section.get("rows") or []
                if idx < len(row) and _parse_number(row[idx]) is not None
            ]
            if not values:
                continue
            header = section["headers"][idx]
            label = header
            if any(existing["label"] == header for existing in kpis):
                label = f"{section['title']} · {header}"
            is_average = any(
                hint in header.lower()
                for hint in ("promedio", "media", "ticket", "margen", "%", "porcentaje")
            )
            total = sum(values) / len(values) if is_average else sum(values)
            kpis.append({
                "label": _short(label, 34),
                "value": _format_number(total, header),
                "helper": (
                    f"promedio de {len(values)} registros"
                    if is_average else f"{len(values)} registros"
                ),
                "section_index": section_index,
                "col_index": idx,
                "aggregate": "avg" if is_average else "sum",
                "header": header,
            })
            if len(kpis) >= 4:
                return kpis
    return kpis


def render_dashboard_html(
    sections: list[dict[str, Any]],
    config: dict,
    period: str,
    title: str | None = None,
    report_type: str = "dashboard",
) -> str:
    """Renderiza un tablero HTML autocontenido (sin scripts)."""
    config = config or {}
    company = config.get("company_name") or "Empresa"
    final_title = title or "Informe"
    normalized = _normalize_sections(sections or [])
    for section in normalized:
        section["numeric_cols"] = _numeric_columns(section)
        section["label_col"] = _label_column(section, section["numeric_cols"])

    charts = []
    for section_index, section in enumerate(normalized):
        if section.get("numeric_cols"):
            bar = _svg_bar(section)
            if bar:
                bar["section_index"] = section_index
                bar["data"]["section_index"] = section_index
                charts.append(bar)
                break
    for section_index, section in enumerate(normalized):
        if section.get("numeric_cols"):
            donut = _svg_donut(section)
            if donut:
                donut["section_index"] = section_index
                donut["data"]["section_index"] = section_index
                charts.append(donut)
                break

    kpis = _build_kpis(normalized)
    report_data = {
        "sections": normalized,
        "kpis": kpis,
        "charts": [c["data"] for c in charts],
    }
    report_data_json = (
        json.dumps(report_data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    footer = _safe_footer(f"{company} | {final_title} | {period}")
    tpl = _env.get_template("dashboard.html")
    return tpl.render(
        company=company,
        title=final_title,
        period=period,
        report_type=report_type,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
        logo=_logo_data_uri(config.get("company_logo")),
        footer_left=footer,
        extra_css="",
        sections=normalized,
        kpis=kpis,
        charts=charts,
        report_data_json=report_data_json,
    )
