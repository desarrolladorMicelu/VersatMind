"""
Conector a SQL Server OFIMA — solo lectura, mediante pyodbc.

Requiere que el servidor tenga instalado el Microsoft ODBC Driver 18
(en el Dockerfile se instala vía msodbcsql18).

Las funciones son síncronas; llámelas desde async con asyncio.to_thread().
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pyodbc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

def _get_connection() -> pyodbc.Connection:
    """Abre una conexión al SQL Server OFIMA con los settings del .env."""
    from mind.config import settings

    conn_str = (
        f"DRIVER={{{settings.SQLSERVER_DRIVER}}};"
        f"SERVER={settings.SQLSERVER_HOST};"
        f"DATABASE={settings.SQLSERVER_DB};"
        f"UID={settings.SQLSERVER_USER};"
        f"PWD={settings.SQLSERVER_PASSWORD};"
        "TrustServerCertificate=yes;"
        "Encrypt=no;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str, timeout=30)


def _rows_to_dicts(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    """Convierte las filas del cursor a lista de dicts con claves en minúsculas."""
    columns = [col[0].lower() for col in cursor.description]
    rows = []
    for row in cursor.fetchall():
        d: dict[str, Any] = {}
        for col, val in zip(columns, row):
            if isinstance(val, (datetime, date)):
                d[col] = val.isoformat()
            elif isinstance(val, Decimal):
                d[col] = float(val)
            else:
                d[col] = val
        rows.append(d)
    return rows


# ---------------------------------------------------------------------------
# Ventas — tabla MvTrade
# ---------------------------------------------------------------------------

def get_sales(start: date, end: date) -> list[dict[str, Any]]:
    """Detalle transaccional de ventas del período (hasta 500 filas)."""
    sql = """
        SELECT TOP 500
            tipodcto, nrodcto, nit, nombre, producto, vendedor, bodega,
            fecha, fhcompra,
            CAST(cantidad  AS DECIMAL(18,4)) AS cantidad,
            CAST(vlrventa  AS DECIMAL(18,2)) AS vlrventa,
            CAST(costo     AS DECIMAL(18,2)) AS costo,
            CAST(descuento AS DECIMAL(18,2)) AS descuento,
            CAST(iva       AS DECIMAL(18,2)) AS iva,
            origen
        FROM MvTrade
        WHERE fhcompra >= ? AND fhcompra < ?
        ORDER BY fhcompra DESC
    """
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


def get_sales_summary(start: date, end: date) -> list[dict[str, Any]]:
    """Resumen mensual de ventas: totales, costo y utilidad bruta."""
    sql = """
        SELECT
            CAST(DATEADD(month, DATEDIFF(month, 0, fhcompra), 0) AS DATE) AS periodo,
            COUNT(*)                                    AS num_transacciones,
            SUM(CAST(vlrventa  AS DECIMAL(18,2)))       AS total_ventas,
            SUM(CAST(costo     AS DECIMAL(18,2)))       AS total_costo,
            SUM(CAST(vlrventa  AS DECIMAL(18,2))
              - CAST(costo     AS DECIMAL(18,2)))       AS utilidad_bruta,
            AVG(CAST(vlrventa  AS DECIMAL(18,2)))       AS promedio_venta
        FROM MvTrade
        WHERE fhcompra >= ? AND fhcompra < ?
        GROUP BY DATEADD(month, DATEDIFF(month, 0, fhcompra), 0)
        ORDER BY periodo DESC
    """
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Cuentas por pagar — vista/tabla VCxP
# ---------------------------------------------------------------------------

def get_cuentas_por_pagar(start: date, end: date) -> list[dict[str, Any]]:
    """CxP del período (hasta 500 filas)."""
    sql = """
        SELECT TOP 500
            tipodcto, nrodcto, fecha, fhvencim, nit, clinombre,
            CAST(bruto      AS DECIMAL(18,2)) AS bruto,
            CAST(descuento  AS DECIMAL(18,2)) AS descuento,
            CAST(ivabruto   AS DECIMAL(18,2)) AS ivabruto,
            CAST(deuda      AS DECIMAL(18,2)) AS deuda,
            CAST(pagado     AS DECIMAL(18,2)) AS pagado,
            mediopag, origen, ciudad, canal
        FROM VCxP
        WHERE fecha >= ? AND fecha < ?
        ORDER BY fecha DESC
    """
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Abonos — vista/tabla VAbonos
# ---------------------------------------------------------------------------

def get_abonos(start: date, end: date) -> list[dict[str, Any]]:
    """Abonos recibidos en el período (hasta 500 filas)."""
    sql = """
        SELECT TOP 500
            documento, fecha, nit,
            CAST(valor AS DECIMAL(18,2)) AS valor,
            banco, concepto
        FROM VAbonos
        WHERE fecha >= ? AND fecha < ?
          AND valor IS NOT NULL AND CAST(valor AS DECIMAL(18,2)) <> 0
        ORDER BY fecha DESC
    """
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Cuadre de caja — vista/tabla MvCuadre
# ---------------------------------------------------------------------------

def get_cuadre_caja(start: date, end: date) -> list[dict[str, Any]]:
    """Movimientos de caja del período (hasta 500 filas)."""
    sql = """
        SELECT TOP 500
            fecha, documento, mediopag, banco,
            CAST(valor AS DECIMAL(18,2)) AS valor,
            nit
        FROM MvCuadre
        WHERE fecha >= ? AND fecha < ?
          AND valor IS NOT NULL AND CAST(valor AS DECIMAL(18,2)) <> 0
        ORDER BY fecha DESC
    """
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Productos — tabla MtMercia
# ---------------------------------------------------------------------------

def get_productos(filtro: str = "") -> list[dict[str, Any]]:
    """Catálogo de productos (hasta 500 filas). Filtra por descripción si se pasa filtro."""
    if filtro:
        sql = """
            SELECT TOP 500
                codigo, descripcio, codlinea, codgrupo,
                CAST(iva AS DECIMAL(18,2)) AS iva,
                habilitado, unidadmed
            FROM MtMercia
            WHERE LOWER(descripcio) LIKE LOWER(?)
            ORDER BY codigo
        """
        params = (f"%{filtro}%",)
    else:
        sql = """
            SELECT TOP 500
                codigo, descripcio, codlinea, codgrupo,
                CAST(iva AS DECIMAL(18,2)) AS iva,
                habilitado, unidadmed
            FROM MtMercia
            ORDER BY codigo
        """
        params = ()

    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, *params)
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Series de utilidad — vista/tabla VSeriesUtilidad
# ---------------------------------------------------------------------------

def get_series_utilidad(start: date, end: date) -> list[dict[str, Any]]:
    """Series de utilidad del período (hasta 1000 filas)."""
    sql = """
        SELECT TOP 1000
            producto, serie, referencia, fecha_inicial, nit,
            CAST(valor AS DECIMAL(18,2)) AS valor,
            documento
        FROM VSeriesUtilidad
        WHERE fecha_inicial BETWEEN ? AND ?
        ORDER BY fecha_inicial DESC
    """
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)
