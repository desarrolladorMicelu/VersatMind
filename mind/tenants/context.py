"""
Contexto de tenant activo para el request actual.
Usa contextvars para ser seguro en async — cada coroutine tiene su propio valor.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mind.db.models import Tenant

# Variable de contexto: se setea al inicio de cada request/handler
_current_tenant: ContextVar["Tenant | None"] = ContextVar("current_tenant", default=None)


def set_tenant(tenant: "Tenant") -> None:
    """Establece el tenant activo para la coroutine actual."""
    _current_tenant.set(tenant)


def get_tenant() -> "Tenant":
    """
    Retorna el tenant activo.
    Lanza RuntimeError si no hay ninguno seteado — indica un bug en el flujo.
    """
    tenant = _current_tenant.get()
    if tenant is None:
        raise RuntimeError(
            "No hay tenant activo en el contexto. "
            "Asegúrate de llamar set_tenant() antes de procesar el request."
        )
    return tenant


def get_tenant_or_none() -> "Tenant | None":
    """Retorna el tenant activo o None si no hay ninguno."""
    return _current_tenant.get()
