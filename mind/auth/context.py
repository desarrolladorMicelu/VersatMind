"""Contexto de permisos para las herramientas del agente."""
from __future__ import annotations

from contextvars import ContextVar

_current_permissions: ContextVar[frozenset[str] | None] = ContextVar(
    "mind_current_permissions", default=None
)


def set_current_permissions(permissions: frozenset[str] | set[str]) -> None:
    _current_permissions.set(frozenset(permissions))


def get_current_permissions() -> frozenset[str] | None:
    return _current_permissions.get()


def has_permission(permission: str) -> bool:
    """Sin contexto explícito se mantiene el comportamiento legado."""
    current = _current_permissions.get()
    if current is None:
        return True
    return permission in current
