"""
Conector a SQL Server OFIMA — solo lectura, mediante pyodbc.

Las funciones reciben un objeto TenantCredentials con las credenciales
del tenant activo, en lugar de leer directamente del settings global.

Requiere que el servidor tenga instalado el Microsoft ODBC Driver 18
(en el Dockerfile se instala vía msodbcsql18).

Las funciones son síncronas; llámelas desde async con asyncio.to_thread().
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pyodbc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Credenciales del tenant
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TenantCredentials:
    host: str
    database: str
    user: str
    password: str
    driver: str = "ODBC Driver 18 for SQL Server"

    @classmethod
    def from_tenant(cls, tenant: Any) -> "TenantCredentials":
        """Construye las credenciales desde un objeto Tenant del ORM."""
        return cls(
            host=tenant.sqlserver_host or "",
            database=tenant.sqlserver_db or "",
            user=tenant.sqlserver_user or "",
            password=tenant.sqlserver_password or "",
            driver=tenant.sqlserver_driver or "ODBC Driver 18 for SQL Server",
        )

    @classmethod
    def from_settings(cls) -> "TenantCredentials":
        """Construye las credenciales desde settings (fallback / testing)."""
        from mind.config import settings
        return cls(
            host=settings.SQLSERVER_HOST,
            database=settings.SQLSERVER_DB,
            user=settings.SQLSERVER_USER,
            password=settings.SQLSERVER_PASSWORD,
            driver=settings.SQLSERVER_DRIVER,
        )

    def is_configured(self) -> bool:
        return bool(self.host and self.password)


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

def _get_connection(creds: TenantCredentials) -> pyodbc.Connection:
    """Abre una conexión al SQL Server con las credenciales del tenant."""
    conn_str = (
        f"DRIVER={{{creds.driver}}};"
        f"SERVER={creds.host};"
        f"DATABASE={creds.database};"
        f"UID={creds.user};"
        f"PWD={creds.password};"
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

def get_sales(start: date, end: date, creds: TenantCredentials) -> list[dict[str, Any]]:
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
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


def get_sales_summary(start: date, end: date, creds: TenantCredentials) -> list[dict[str, Any]]:
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
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Cuentas por pagar — vista/tabla VCxP
# ---------------------------------------------------------------------------

def get_cuentas_por_pagar(start: date, end: date, creds: TenantCredentials) -> list[dict[str, Any]]:
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
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Abonos — vista/tabla VAbonos
# ---------------------------------------------------------------------------

def get_abonos(start: date, end: date, creds: TenantCredentials) -> list[dict[str, Any]]:
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
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Cuadre de caja — vista/tabla MvCuadre
# ---------------------------------------------------------------------------

def get_cuadre_caja(start: date, end: date, creds: TenantCredentials) -> list[dict[str, Any]]:
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
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Productos — tabla MtMercia
# ---------------------------------------------------------------------------

def get_productos(filtro: str = "", *, creds: TenantCredentials) -> list[dict[str, Any]]:
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

    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, *params)
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# Series de utilidad — vista/tabla VSeriesUtilidad
# ---------------------------------------------------------------------------

def get_series_utilidad(start: date, end: date, creds: TenantCredentials) -> list[dict[str, Any]]:
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
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)
