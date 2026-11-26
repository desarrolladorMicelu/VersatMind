"""Descarga y previsualización autenticada de informes HTML."""
from __future__ import annotations

import asyncio
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import get_effective_tenant_id, require_admin
from mind.db.base import get_session
from mind.db.models import Report

router = APIRouter(prefix="/api/admin/reports", tags=["reports"])

_CSP = (
    "sandbox allow-scripts allow-downloads; default-src 'none'; "
    "script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; font-src data:; connect-src 'none'; frame-ancestors 'self'"
)


def _owner(admin: dict) -> str:
    return str(admin.get("sub") or "admin")


def _filename(report: Report) -> str:
    base = f"{report.title}_{report.period}".strip("_")
    base = re.sub(r"[^A-Za-z0-9 _.-]", "_", base).strip() or "informe"
    return f"{base[:80]}.html"


async def _load(
    report_id: int,
    admin: dict,
    tenant_id: int | None,
    session: AsyncSession,
) -> Report:
    tid = get_effective_tenant_id(admin, tenant_id)
    report = (await session.execute(
        select(Report).where(
            Report.id == report_id,
            Report.tenant_id == tid,
            Report.owner == _owner(admin),
        )
    )).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Informe no encontrado")
    return report


@router.get("/{report_id}/html", response_class=HTMLResponse)
async def report_html(
    report_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    report = await _load(report_id, admin, tenant_id, session)
    return HTMLResponse(
        content=report.html,
        headers={
            "Content-Security-Policy": _CSP,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{_filename(report)}"',
        },
    )


@router.get("/{report_id}/download")
async def report_download(
    report_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    report = await _load(report_id, admin, tenant_id, session)
    return Response(
        content=report.html,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": _CSP,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{_filename(report)}"',
        },
    )


@router.get("/{report_id}/pdf")
async def report_pdf(
    report_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    report = await _load(report_id, admin, tenant_id, session)
    from mind.reports.service import can_generate_pdf
    if not can_generate_pdf():
        raise HTTPException(
            status_code=503,
            detail="La exportación a PDF no está disponible en este servidor.",
        )
    try:
        from mind.reports.generator import generate_custom_report
        from mind.db.models import Tenant
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="La exportación a PDF no está disponible en este servidor.",
        )

    try:
        # Reutiliza la plantilla PDF de VT-51 con las mismas secciones
        # guardadas para el tablero web.
        pdf_bytes: bytes
        if report.sections:
            tenant_obj = await session.get(Tenant, report.tenant_id)
            config = getattr(tenant_obj, "report_config", None) or {}
            file_path = await generate_custom_report(
                sections=report.sections,
                report_config=config,
                period=report.period,
                title=report.title,
            )
            with open(file_path, "rb") as fh:
                pdf_bytes = fh.read()
            try:
                os.unlink(file_path)
                parent = os.path.dirname(file_path)
                if os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
            except Exception:
                pass
        else:
            from weasyprint import HTML
            pdf_bytes = await asyncio.to_thread(
                lambda: HTML(string=report.html).write_pdf()
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo generar el PDF: {exc}")

    filename = _filename(report).rsplit(".", 1)[0] + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


