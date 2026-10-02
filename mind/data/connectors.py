"""
Conectores de datos para Mind by Versat.
Fachada que obtiene las credenciales del tenant activo y delega a sqlserver.py.
Las funciones son síncronas: llámelas desde async con asyncio.to_thread().
"""
from __future__ import annotations

from datetime import date
from typing import Any

from mind.data.sqlserver import (
    TenantCredentials,
    get_sales as _get_sales,
    get_sales_summary as _get_sales_summary,
    get_cuentas_por_pagar as _get_cxp,
    get_abonos as _get_abonos,
    get_cuadre_caja as _get_cuadre_caja,
    get_productos as _get_productos,
    get_series_utilidad as _get_series_utilidad,
    get_catalogo_precios as _get_catalogo_precios,
    get_stock_celulares as _get_stock_celulares,
    get_gangazos as _get_gangazos,
    get_ventas_recientes as _get_ventas_recientes,
    get_inventario_bodega as _get_inventario_bodega,
    get_imei as _get_imei,
    get_historial_cliente as _get_historial_cliente,
    get_cliente_por_nit as _get_cliente_por_nit,
    get_direccion_proveedor as _get_direccion_proveedor,
    get_estado_sync_clientes as _get_estado_sync_clientes,
    get_inventario_activos as _get_inventario_activos,
    get_cliente_completo as _get_cliente_completo,
    get_factura_reciente as _get_factura_reciente,
    get_medios_pago as _get_medios_pago,
    get_movimientos_contables as _get_movimientos_contables,
)


def _creds(tenant_creds: TenantCredentials | None = None) -> TenantCredentials:
    """Resuelve las credenciales: usa las del tenant si se pasan, sino el contexto activo."""
    if tenant_creds is not None:
        return tenant_creds
    # Intentar obtener del contexto de tenant activo
    try:
        from mind.tenants.context import get_tenant
        return TenantCredentials.from_tenant(get_tenant())
    except RuntimeError:
        # Fuera de contexto de request (ej: tests) → usar settings
        return TenantCredentials.from_settings()


def get_sales(start: date, end: date, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_sales(start, end, _creds(creds))


def get_sales_summary(start: date, end: date, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_sales_summary(start, end, _creds(creds))


def get_cuentas_por_pagar(start: date, end: date, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_cxp(start, end, _creds(creds))


def get_abonos(start: date, end: date, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_abonos(start, end, _creds(creds))


def get_cuadre_caja(start: date, end: date, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_cuadre_caja(start, end, _creds(creds))


def get_productos(filtro: str = "", creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_productos(filtro, creds=_creds(creds))


def get_series_utilidad(start: date, end: date, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_series_utilidad(start, end, _creds(creds))


# ── Consultas adicionales ─────────────────────────────────────────────────────

def get_catalogo_precios(filtro: str = "", limite: int = 200, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_catalogo_precios(filtro, limite, creds=_creds(creds))


def get_stock_celulares(creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_stock_celulares(creds=_creds(creds))


def get_gangazos(creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_gangazos(creds=_creds(creds))


def get_ventas_recientes(dias: int = 90, limite: int = 1000, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_ventas_recientes(dias, limite, creds=_creds(creds))


def get_inventario_bodega(bodega: str, limite: int = 1000, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_inventario_bodega(bodega, limite, creds=_creds(creds))


def get_imei(imei: str, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_imei(imei, creds=_creds(creds))


def get_historial_cliente(nit: str, limite: int = 200, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_historial_cliente(nit, limite, creds=_creds(creds))


def get_cliente_por_nit(nit: str, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_cliente_por_nit(nit, creds=_creds(creds))


def get_direccion_proveedor(nombre: str, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_direccion_proveedor(nombre, creds=_creds(creds))


def get_estado_sync_clientes(creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_estado_sync_clientes(creds=_creds(creds))


def get_inventario_activos(limite: int = 2000, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_inventario_activos(limite, creds=_creds(creds))


def get_cliente_completo(nit: str, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_cliente_completo(nit, creds=_creds(creds))


def get_factura_reciente(nit: str, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_factura_reciente(nit, creds=_creds(creds))


def get_medios_pago(creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_medios_pago(creds=_creds(creds))


def get_movimientos_contables(start: date, end: date, limite: int = 500, creds: TenantCredentials | None = None) -> list[dict[str, Any]]:
    return _get_movimientos_contables(start, end, limite, creds=_creds(creds))
