"""Contexto de generación de informes para las herramientas del agente."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class ReportContext:
    tenant_id: int | None = None
    owner: str | None = None
    conversation_id: int | None = None
    chat_id: int | None = None
    channel: str = "telegram"


_report_context: ContextVar[ReportContext | None] = ContextVar(
    "mind_report_context", default=None
)


def set_report_context(
    *,
    tenant_id: int | None,
    owner: str | None = None,
    conversation_id: int | None = None,
    chat_id: int | None = None,
    channel: str = "telegram",
) -> None:
    _report_context.set(ReportContext(
        tenant_id=tenant_id,
        owner=owner,
        conversation_id=conversation_id,
        chat_id=chat_id,
        channel=channel,
    ))


def get_report_context() -> ReportContext | None:
    return _report_context.get()
