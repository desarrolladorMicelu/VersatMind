"""
Conectores de datos para Mind by Versat.

Fachada única para las consultas OFIMA. Delega en sqlserver.py (pyodbc)
cuando SQLSERVER_HOST está configurado; cae a la copia PostgreSQL de Railway
(OFIMA_DATABASE_URL) como fallback de último recurso.

Las funciones son síncronas: llámelas desde async con asyncio.to_thread().
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def _use_sqlserver() -> bool:
    """True cuando las variables de SQL Server están configuradas."""
    from mind.config import settings
    return bool(settings.SQLSERVER_HOST and settings.SQLSERVER_PASSWORD)


# ---------------------------------------------------------------------------
# Ventas
# ---------------------------------------------------------------------------

def get_sales(start: date, end: date) -> list[dict[str, Any]]:
    if _use_sqlserver():
        from mind.data.sqlserver import get_sales as _get
        return _get(start, end)
    return _pg_sales(start, end)


def get_sales_summary(start: date, end: date) -> list[dict[str, Any]]:
    if _use_sqlserver():
        from mind.data.sqlserver import get_sales_summary as _get
        return _get(start, end)
    return _pg_sales_summary(start, end)


# ---------------------------------------------------------------------------
# Finanzas
# ---------------------------------------------------------------------------

def get_cuentas_por_pagar(start: date, end: date) -> list[dict[str, Any]]:
    if _use_sqlserver():
        from mind.data.sqlserver import get_cuentas_por_pagar as _get
        return _get(start, end)
    return _pg_cxp(start, end)


def get_abonos(start: date, end: date) -> list[dict[str, Any]]:
    if _use_sqlserver():
        from mind.data.sqlserver import get_abonos as _get
        return _get(start, end)
    return _pg_abonos(start, end)


def get_cuadre_caja(start: date, end: date) -> list[dict[str, Any]]:
    if _use_sqlserver():
        from mind.data.sqlserver import get_cuadre_caja as _get
        return _get(start, end)
    return _pg_cuadre_caja(start, end)


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

def get_productos(filtro: str = "") -> list[dict[str, Any]]:
    if _use_sqlserver():
        from mind.data.sqlserver import get_productos as _get
        return _get(filtro)
    return _pg_productos(filtro)


# ---------------------------------------------------------------------------
# Series de utilidad
# ---------------------------------------------------------------------------

def get_series_utilidad(start: date, end: date) -> list[dict[str, Any]]:
    if _use_sqlserver():
        from mind.data.sqlserver import get_series_utilidad as _get
        return _get(start, end)
    return _pg_series_utilidad(start, end)


# ---------------------------------------------------------------------------
# Fallback PostgreSQL Railway (backups OFIMA) — solo lectura
# ---------------------------------------------------------------------------

def _pg_conn():
    import psycopg2
    from mind.config import settings
    return psycopg2.connect(settings.OFIMA_DATABASE_URL, connect_timeout=30)


def _pg_rows(cursor) -> list[dict[str, Any]]:
    from datetime import datetime
    columns = [col.name for col in cursor.description]
    rows = []
    for row in cursor.fetchall():
        d = {}
        for col, val in zip(columns, row):
            d[col] = val.isoformat() if isinstance(val, (datetime, date)) else val
        rows.append(d)
    return rows


def _pg_sales(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT tipodcto, nrodcto, nit, nombre, producto, vendedor, bodega,
               fecha, fhcompra,
               cantidad::numeric AS cantidad, vlrventa::numeric AS vlrventa,
               costo::numeric AS costo, descuento::numeric AS descuento,
               iva::numeric AS iva, origen
        FROM backups.mvtrade
        WHERE fhcompra >= %s AND fhcompra < %s
        ORDER BY fhcompra DESC LIMIT 500
    """
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _pg_rows(cur)


def _pg_sales_summary(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT DATE_TRUNC('month', fhcompra)::date AS periodo,
               COUNT(*) AS num_transacciones,
               SUM(vlrventa::numeric) AS total_ventas,
               SUM(costo::numeric) AS total_costo,
               SUM(vlrventa::numeric - costo::numeric) AS utilidad_bruta,
               AVG(vlrventa::numeric) AS promedio_venta
        FROM backups.mvtrade
        WHERE fhcompra >= %s AND fhcompra < %s
        GROUP BY DATE_TRUNC('month', fhcompra)
        ORDER BY periodo DESC
    """
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _pg_rows(cur)


def _pg_cxp(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT tipodcto, nrodcto, fecha, fhvencim, nit, clinombre,
               bruto::numeric AS bruto, descuento::numeric AS descuento,
               ivabruto::numeric AS ivabruto, deuda::numeric AS deuda,
               pagado::numeric AS pagado, mediopag, origen, ciudad, canal
        FROM backups.vcxp
        WHERE fecha >= %s AND fecha < %s
        ORDER BY fecha DESC LIMIT 500
    """
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _pg_rows(cur)


def _pg_abonos(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT documento, fecha, nit, valor::numeric AS valor, banco, concepto
        FROM backups.vabonos
        WHERE fecha >= %s AND fecha < %s
          AND valor IS NOT NULL AND valor::numeric <> 0
        ORDER BY fecha DESC LIMIT 500
    """
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _pg_rows(cur)


def _pg_cuadre_caja(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT fecha, documento, mediopag, banco, valor::numeric AS valor, nit
        FROM backups.mvcuadre
        WHERE fecha >= %s AND fecha < %s
          AND valor IS NOT NULL AND valor::numeric <> 0
        ORDER BY fecha DESC LIMIT 500
    """
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _pg_rows(cur)


def _pg_productos(filtro: str = "") -> list[dict[str, Any]]:
    if filtro:
        sql = """
            SELECT codigo, descripcio, codlinea, codgrupo,
                   iva::numeric AS iva, habilitado, unidadmed
            FROM backups.mtmercia
            WHERE LOWER(descripcio) LIKE LOWER(%s)
            ORDER BY codigo LIMIT 500
        """
        with _pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (f"%{filtro}%",))
                return _pg_rows(cur)
    else:
        sql = """
            SELECT codigo, descripcio, codlinea, codgrupo,
                   iva::numeric AS iva, habilitado, unidadmed
            FROM backups.mtmercia ORDER BY codigo LIMIT 500
        """
        with _pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return _pg_rows(cur)


def _pg_series_utilidad(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT producto, serie, referencia, fecha_inicial, nit,
               valor::numeric AS valor, documento
        FROM backups.vseriesutilidad
        WHERE fecha_inicial BETWEEN %s AND %s
        ORDER BY fecha_inicial DESC LIMIT 1000
    """
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _pg_rows(cur)
