"""
Conectores de datos para Mind by Versat.
Consultas al esquema backups en PostgreSQL Railway — solo lectura.
Las columnas numéricas se castean a NUMERIC porque están almacenadas como TEXT.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def _get_connection():
    from mind.config import settings
    return psycopg2.connect(settings.OFIMA_DATABASE_URL, connect_timeout=30)


def _rows_to_dicts(cursor) -> list[dict[str, Any]]:
    columns = [col.name for col in cursor.description]
    rows = []
    for row in cursor.fetchall():
        d = {}
        for col, val in zip(columns, row):
            d[col] = val.isoformat() if isinstance(val, (datetime, date)) else val
        rows.append(d)
    return rows


def get_sales(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT tipodcto, nrodcto, nit, nombre, producto, vendedor, bodega,
               fecha, fhcompra,
               cantidad::numeric AS cantidad,
               vlrventa::numeric AS vlrventa,
               costo::numeric AS costo,
               descuento::numeric AS descuento,
               iva::numeric AS iva,
               origen
        FROM backups.mvtrade
        WHERE fhcompra >= %s AND fhcompra < %s
        ORDER BY fhcompra DESC
        LIMIT 500
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _rows_to_dicts(cur)


def get_sales_summary(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT
            DATE_TRUNC('month', fhcompra)::date AS periodo,
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
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _rows_to_dicts(cur)


def get_cuentas_por_pagar(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT tipodcto, nrodcto, fecha, fhvencim, nit, clinombre,
               bruto::numeric AS bruto,
               descuento::numeric AS descuento,
               ivabruto::numeric AS ivabruto,
               deuda::numeric AS deuda,
               pagado::numeric AS pagado,
               mediopag, origen, ciudad, canal
        FROM backups.vcxp
        WHERE fecha >= %s AND fecha < %s
        ORDER BY fecha DESC
        LIMIT 500
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _rows_to_dicts(cur)


def get_abonos(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT documento, fecha, nit,
               valor::numeric AS valor,
               banco, concepto
        FROM backups.vabonos
        WHERE fecha >= %s AND fecha < %s
          AND valor IS NOT NULL AND valor::numeric <> 0
        ORDER BY fecha DESC
        LIMIT 500
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _rows_to_dicts(cur)


def get_cuadre_caja(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT fecha, documento, mediopag, banco,
               valor::numeric AS valor,
               nit
        FROM backups.mvcuadre
        WHERE fecha >= %s AND fecha < %s
          AND valor IS NOT NULL AND valor::numeric <> 0
        ORDER BY fecha DESC
        LIMIT 500
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _rows_to_dicts(cur)


def get_productos(filtro: str = "") -> list[dict[str, Any]]:
    if filtro:
        sql = """
            SELECT codigo, descripcio, codlinea, codgrupo,
                   iva::numeric AS iva,
                   habilitado, unidadmed
            FROM backups.mtmercia
            WHERE LOWER(descripcio) LIKE LOWER(%s)
            ORDER BY codigo
            LIMIT 500
        """
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (f"%{filtro}%",))
                return _rows_to_dicts(cur)
    else:
        sql = """
            SELECT codigo, descripcio, codlinea, codgrupo,
                   iva::numeric AS iva,
                   habilitado, unidadmed
            FROM backups.mtmercia
            ORDER BY codigo
            LIMIT 500
        """
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return _rows_to_dicts(cur)


def get_series_utilidad(start: date, end: date) -> list[dict[str, Any]]:
    sql = """
        SELECT producto, serie, referencia, fecha_inicial, nit,
               valor::numeric AS valor,
               documento
        FROM backups.vseriesutilidad
        WHERE fecha_inicial BETWEEN %s AND %s
        ORDER BY fecha_inicial DESC
        LIMIT 1000
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(start), str(end)))
            return _rows_to_dicts(cur)
