"""
Conectores de datos para Mind by Versat.
Consultas a SQL Server OFIMA mediante pyodbc — solo lectura.
Las funciones son síncronas: llámelas desde async con asyncio.to_thread().
"""
from __future__ import annotations

from datetime import date
from typing import Any

from mind.data.sqlserver import (
    get_sales,
    get_sales_summary,
    get_cuentas_por_pagar,
    get_abonos,
    get_cuadre_caja,
    get_productos,
    get_series_utilidad,
)

__all__ = [
    "get_sales",
    "get_sales_summary",
    "get_cuentas_por_pagar",
    "get_abonos",
    "get_cuadre_caja",
    "get_productos",
    "get_series_utilidad",
]
