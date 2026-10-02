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


# ---------------------------------------------------------------------------
# Consultas adicionales útiles para la IA
# ---------------------------------------------------------------------------

def get_catalogo_precios(
    filtro: str = "", limite: int = 200, *, creds: TenantCredentials
) -> list[dict[str, Any]]:
    """Catálogo de productos con precio, marca/categoría (MvPrecio + MtMercia)."""
    limite = max(1, min(int(limite or 200), 2000))
    where = ""
    params: tuple = ()
    if filtro:
        where = "WHERE MtMercia.DESCRIPCIO LIKE ? OR MvPrecio.CODPRODUC LIKE ?"
        params = (f"%{filtro}%", f"%{filtro}%")
    sql = f"""
        SELECT TOP {limite}
            MvPrecio.CODPRODUC, MvPrecio.CODPRECIO, MvPrecio.PRECIO,
            MtMercia.DESCRIPCIO, MtMercia.CLASIFICA2, MtMercia.CODLINEA,
            MtMercia.CODSBLIN, MtMercia.HABILITADO, MtMercia.UBICACION
        FROM MvPrecio
        INNER JOIN MtMercia ON MvPrecio.CODPRODUC = MtMercia.CODIGO
        {where}
        ORDER BY MtMercia.DESCRIPCIO
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, *params)
        return _rows_to_dicts(cur)


def get_stock_celulares(*, creds: TenantCredentials) -> list[dict[str, Any]]:
    """Stock de celulares por referencia y bodega (en tiempo real)."""
    sql = """
        SELECT MTSERIES.CODIGO, MtMercia.DESCRIPCIO, COUNT(MTSERIES.SERIE) AS cantidad
        FROM MTSERIES
        INNER JOIN MtMercia ON MTSERIES.CODIGO = MtMercia.CODIGO
        WHERE MTSERIES.EXISTE = 1
          AND MtMercia.CODLINEA = 'CEL'
          AND MTSERIES.BODEGA IN ('BM','BB','TB','TM','BCAL','BNQS','BTPI','TPI')
        GROUP BY MTSERIES.CODIGO, MtMercia.DESCRIPCIO
        ORDER BY cantidad DESC
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return _rows_to_dicts(cur)


def get_gangazos(*, creds: TenantCredentials) -> list[dict[str, Any]]:
    """Equipos de servicio técnico listos para venta como gangazo (estado 'C')."""
    sql = """
        SELECT XMYCT_TECNICO_SERIES.XSERIE, XMYCT_TECNICO_SERIES.XNOTA,
               XMYCT_TECNICO_SERIES.XESTADO, MTSERIES.CODIGO,
               MTSERIES.EXISTE, MtMercia.DESCRIPCIO
        FROM XMYCT_TECNICO_SERIES
        INNER JOIN MTSERIES ON MTSERIES.SERIE = XMYCT_TECNICO_SERIES.XSERIE
        INNER JOIN MtMercia ON MTSERIES.CODIGO = MtMercia.CODIGO
        WHERE XMYCT_TECNICO_SERIES.XESTADO = 'C'
          AND MTSERIES.EXISTE = 1
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return _rows_to_dicts(cur)


def get_ventas_recientes(
    dias: int = 90, limite: int = 1000, *, creds: TenantCredentials
) -> list[dict[str, Any]]:
    """Ventas de los últimos N días desde la vista ventas_bodega."""
    dias = max(1, min(int(dias or 90), 3650))
    limite = max(1, min(int(limite or 1000), 5000))
    sql = f"""
        SELECT TOP {limite}
            TipoDcto, nrodcto, fecha, Serie, DESCRIPCIO,
            Nombre_vendedor, Nit, codven
        FROM ventas_bodega
        WHERE fecha >= DATEADD(DAY, -{dias}, GETDATE())
          AND TipoDcto IN ('FB','FM','FI')
        ORDER BY fecha DESC
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return _rows_to_dicts(cur)


def get_inventario_bodega(
    bodega: str, limite: int = 1000, *, creds: TenantCredentials
) -> list[dict[str, Any]]:
    """Inventario físico (IMEI a IMEI) de una bodega para arqueo."""
    limite = max(1, min(int(limite or 1000), 5000))
    sql = f"""
        SELECT TOP {limite}
            MTSERIES.SERIE, MtMercia.DESCRIPCIO, MTSERIES.CODIGO, MTSERIES.BODEGA
        FROM MTSERIES
        INNER JOIN MtMercia ON MTSERIES.CODIGO = MtMercia.CODIGO
        WHERE MTSERIES.EXISTE = 1
          AND MTSERIES.BODEGA = ?
          AND MtMercia.CODLINEA IN ('CEL','CYT')
        ORDER BY MtMercia.DESCRIPCIO
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, bodega)
        return _rows_to_dicts(cur)


def get_imei(imei: str, *, creds: TenantCredentials) -> list[dict[str, Any]]:
    """Valida un IMEI/serie: si existe, en qué bodega y qué producto es."""
    sql = """
        SELECT TOP 20
            MtMercia.DESCRIPCIO, MTSERIES.BODEGA, MTSERIES.CODIGO,
            MTSERIES.EXISTE, MTSERIES.SERIE
        FROM MTSERIES
        INNER JOIN MtMercia ON MTSERIES.CODIGO = MtMercia.CODIGO
        WHERE MTSERIES.EXISTE = 1
          AND MtMercia.CODLINEA IN ('CEL','CYT')
          AND (MTSERIES.SERIE = ? OR LEFT(MTSERIES.SERIE, 15) = LEFT(?, 15))
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, imei, imei)
        return _rows_to_dicts(cur)


def get_historial_cliente(
    nit: str, limite: int = 200, *, creds: TenantCredentials
) -> list[dict[str, Any]]:
    """Historial de compras de un cliente por NIT."""
    limite = max(1, min(int(limite or 200), 2000))
    sql = f"""
        SELECT TOP {limite}
            m.NOMBRE, m.VLRVENTA, m.FHCOMPRA, m.TIPODCTO
        FROM Clientes c
        JOIN V_CLIENTES_FAC vc ON c.NOMBRE = vc.NOMBRE
        JOIN Mvtrade m ON vc.tipoDcto = m.Tipodcto AND vc.nroDcto = m.NRODCTO
        WHERE c.HABILITADO = 'S'
          AND (c.NIT = ? OR c.NIT LIKE ?)
          AND m.VLRVENTA > 0
          AND m.TIPODCTO IN ('FM','FB','FC')
        ORDER BY m.FHCOMPRA DESC
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, nit, f"%{nit}%")
        return _rows_to_dicts(cur)


def get_cliente_por_nit(nit: str, *, creds: TenantCredentials) -> list[dict[str, Any]]:
    """Busca un cliente por NIT/cédula."""
    sql = """
        SELECT TOP 20 NOMBRE, NIT
        FROM Clientes
        WHERE NIT = ? OR NIT LIKE ?
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, nit, f"%{nit}%")
        return _rows_to_dicts(cur)


def get_direccion_proveedor(nombre: str, *, creds: TenantCredentials) -> list[dict[str, Any]]:
    """Dirección registrada de un proveedor por nombre."""
    sql = """
        SELECT TOP 1 nombre, direccion
        FROM MTPROCLI
        WHERE UPPER(LTRIM(RTRIM(nombre))) = UPPER(LTRIM(RTRIM(?)))
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, nombre)
        return _rows_to_dicts(cur)


def get_estado_sync_clientes(*, creds: TenantCredentials) -> list[dict[str, Any]]:
    """Estado de sincronización de clientes entre ventas y Ofima."""
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*)
            FROM ESPCLIENTES e
            LEFT JOIN MTPROCLI m ON e.NIT = m.NIT
            WHERE m.NIT IS NULL
        """)
        pendientes = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*)
            FROM MTPROCLI
            WHERE fechaing >= DATEADD(hour, -1, GETDATE())
        """)
        recientes = cur.fetchone()[0]
    return [{
        "clientes_pendientes_sincronizar": int(pendientes),
        "clientes_sincronizados_ultima_hora": int(recientes),
    }]


def get_inventario_activos(
    limite: int = 2000, *, creds: TenantCredentials
) -> list[dict[str, Any]]:
    """Equipos activos en inventario (todas las líneas) con su descripción."""
    limite = max(1, min(int(limite or 2000), 10000))
    sql = f"""
        SELECT TOP {limite}
            MTSERIES.SERIE, MtMercia.DESCRIPCIO
        FROM MTSERIES
        INNER JOIN MtMercia ON MTSERIES.CODIGO = MtMercia.CODIGO
        WHERE MTSERIES.TIPODCTO IN ('FP','EQ','FM','FB','ET','FI')
          AND MTSERIES.EXISTE = 1
        ORDER BY MtMercia.DESCRIPCIO
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return _rows_to_dicts(cur)


def get_cliente_completo(nit: str, *, creds: TenantCredentials) -> list[dict[str, Any]]:
    """Datos completos de un cliente por NIT (para documentos/firmas)."""
    sql = """
        SELECT TOP 1 nit, nombre, direccion, tel1, tel2, email, emailfec, nombre1, nombre2
        FROM MTPROCLI
        WHERE nit = ? OR nit LIKE ?
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, nit, f"%{nit}%")
        return _rows_to_dicts(cur)


def get_factura_reciente(nit: str, *, creds: TenantCredentials) -> list[dict[str, Any]]:
    """Factura más reciente de un cliente (para asociar pedidos online)."""
    sql = """
        SELECT TOP 1 TIPODCTO, NRODCTO, FHCOMPRA, VLRVENTA
        FROM Mvtrade
        WHERE (NIT = ? OR NIT LIKE ?)
          AND TIPODCTO IN ('FM','FB','FC')
          AND VLRVENTA > 0
        ORDER BY FHCOMPRA DESC
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, nit, f"%{nit}%")
        return _rows_to_dicts(cur)


def get_medios_pago(*, creds: TenantCredentials) -> list[dict[str, Any]]:
    """Medios de pago / bancos registrados en Ofima."""
    sql = "SELECT DESCRIPCIO, CODIGOCTA, CONCEPTO FROM MTMEDPAG ORDER BY DESCRIPCIO"
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return _rows_to_dicts(cur)


def get_movimientos_contables(
    start: date, end: date, limite: int = 500, *, creds: TenantCredentials
) -> list[dict[str, Any]]:
    """Movimientos contables/caja del período con tercero y ciudad (MVTO + MtProcli)."""
    limite = max(1, min(int(limite or 500), 5000))
    sql = f"""
        SELECT TOP {limite}
            m.FECHAMVTO, m.DCTO, m.DESCRIPCIO, m.CODIGOCTA,
            m.CREDITO, m.DEBITO, m.NIT,
            p.NOMBRE AS tercero, p.CIUDAD
        FROM MVTO m
        LEFT JOIN MTPROCLI p ON m.NIT = p.NIT
        WHERE m.FECHAMVTO >= ? AND m.FECHAMVTO < ?
        ORDER BY m.FECHAMVTO DESC
    """
    with _get_connection(creds) as conn:
        cur = conn.cursor()
        cur.execute(sql, str(start), str(end))
        return _rows_to_dicts(cur)
