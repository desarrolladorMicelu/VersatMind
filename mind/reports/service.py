"""Servicio de informes HTML para el chat web."""
from __future__ import annotations

import importlib.util
from typing import Any

from sqlalchemy import select, update

from mind.reports.context import get_report_context
from mind.reports.dashboard import render_dashboard_html
from mind.reports.generator import _normalize_sections


def can_generate_pdf() -> bool:
    return importlib.util.find_spec("weasyprint") is not None


def report_meta(report) -> dict[str, Any]:
    return {
        "id": report.id,
        "title": report.title,
        "period": report.period,
        "type": report.report_type,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "html_url": f"/api/admin/reports/{report.id}/html?tenant_id={report.tenant_id}",
        "download_url": f"/api/admin/reports/{report.id}/download?tenant_id={report.tenant_id}",
        "pdf_url": (
            f"/api/admin/reports/{report.id}/pdf?tenant_id={report.tenant_id}"
            if can_generate_pdf() else None
        ),
        "can_pdf": can_generate_pdf(),
    }


async def create_web_report(
    *,
    sections: list[dict[str, Any]],
    title: str,
    period: str,
    report_type: str,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """
    Persiste un tablero HTML para la conversación web actual.
    Retorna None si no hay contexto web o base de datos disponible.
    """
    ctx = get_report_context()
    if ctx is None or ctx.tenant_id is None or ctx.channel != "web":
        return None

    from mind.db.base import _session_factory
    from mind.db.models import Report

    if _session_factory is None:
        return None

    normalized = _normalize_sections(sections or [])
    html = render_dashboard_html(
        normalized, config or {}, period, title, report_type,
    )

    async with _session_factory() as session:
        report = Report(
            tenant_id=ctx.tenant_id,
            owner=ctx.owner,
            conversation_id=ctx.conversation_id,
            chat_id=ctx.chat_id,
            title=title[:160],
            period=period[:120],
            report_type=report_type[:60],
            html=html,
            sections=normalized,
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        return report_meta(report)


async def link_reports_to_message(
    report_ids: list[int],
    *,
    tenant_id: int,
    message_id: int,
) -> None:
    if not report_ids:
        return
    from mind.db.base import _session_factory
    from mind.db.models import Report

    if _session_factory is None:
        return
    async with _session_factory() as session:
        await session.execute(
            update(Report)
            .where(Report.id.in_(report_ids), Report.tenant_id == tenant_id)
            .values(message_id=message_id)
        )
        await session.commit()


async def get_report(report_id: int, *, tenant_id: int, owner: str):
    from mind.db.base import _session_factory
    from mind.db.models import Report

    if _session_factory is None:
        return None
    async with _session_factory() as session:
        return (await session.execute(
            select(Report).where(
                Report.id == report_id,
                Report.tenant_id == tenant_id,
                Report.owner == owner,
            )
        )).scalar_one_or_none()
