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
