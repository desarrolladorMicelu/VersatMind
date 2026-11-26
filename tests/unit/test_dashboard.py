"""Tests del renderizador de tableros HTML (sin scripts)."""
from mind.reports.dashboard import render_dashboard_html


def test_dashboard_has_kpis_charts_and_self_contained_js():
    html = render_dashboard_html(
        [
            {
                "title": "Ventas por mes",
                "headers": ["Mes", "Ventas", "Transacciones"],
                "rows": [
                    ["Enero", "1.000.000", 10],
                    ["Febrero", "1.500.000", 15],
                    ["Marzo", "900.000", 8],
                ],
                "summary": "Crecimiento sostenido",
            },
            {
                "title": "Cartera",
                "headers": ["Proveedor", "Deuda"],
                "rows": [
                    ["Proveedor A", "500.000"],
                    ["Proveedor B", "750.000"],
                ],
                "summary": None,
            },
        ],
        {"company_name": "MICELU"},
        "2026",
        "Tablero comercial",
        "Tablero",
    )
    assert "Tablero comercial" in html
    assert 'class="kpi"' in html
    assert "<svg" in html
    assert "<script" in html.lower()
    assert 'src="http' not in html
    assert "mind-report-data" in html
    assert "Proveedor A" in html
    assert "MICELU" in html
