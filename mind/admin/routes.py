"""
API REST del panel de administración — /api/admin/*
Multi-tenant: los endpoints de datos aceptan ?tenant_id= para filtrar.
Los endpoints de tenants permiten CRUD completo de tenants.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import create_access_token, require_admin, verify_credentials
from mind.db.base import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin-api"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class AgentConfigUpdate(BaseModel):
    system_prompt: str
    model: str
    temperature: float
    conversation_window: int
    max_tool_cycles: int

class RolePermissionsUpdate(BaseModel):
    permissions: list[str]

class NewRole(BaseModel):
    name: str
    description: str = ""
    tenant_id: int

class ExternalDbPayload(BaseModel):
    engine: str = "postgresql"
    host: str = ""
    port: int = 5432
    database: str = ""
    user: str = ""
    password: str = ""

class ExternalSheetsPayload(BaseModel):
    spreadsheet_url: str = ""
    credentials: dict | None = None

class TenantCreate(BaseModel):
    name: str
    slug: str
    bot_token: str
    webhook_url: str
    admin_chat_id: int
    sqlserver_host: str = ""
    sqlserver_db: str = ""
    sqlserver_user: str = ""
    sqlserver_password: str = ""
    sqlserver_driver: str = "ODBC Driver 18 for SQL Server"
    external_db: dict | None = None
    external_sheets: dict | None = None

class TenantUpdate(BaseModel):
    name: str | None = None
    bot_token: str | None = None
    webhook_url: str | None = None
    admin_chat_id: int | None = None
    sqlserver_host: str | None = None
    sqlserver_db: str | None = None
    sqlserver_user: str | None = None
    sqlserver_password: str | None = None
    sqlserver_driver: str | None = None
    is_active: bool | None = None
    external_db: dict | None = None
    external_sheets: dict | None = None


# ── AUTH ─────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(body: LoginRequest, response: Response):
    if not verify_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = create_access_token(body.username)
    response.set_cookie(
        "admin_token", token,
        httponly=True, samesite="lax",
        max_age=86400, path="/",
    )
    return {"token": token, "username": body.username}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("admin_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(admin=Depends(require_admin)):
    return {"username": admin.get("sub")}


# ── TENANTS ──────────────────────────────────────────────────────────────────

@router.get("/tenants")
async def tenants_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenants = (await session.execute(
        select(Tenant).order_by(Tenant.created_at.desc())
    )).scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "is_active": t.is_active,
            "bot_token_hint": f"...{t.bot_token[-6:]}",
            "webhook_url": t.webhook_url,
            "admin_chat_id": t.admin_chat_id,
            "sqlserver_host": t.sqlserver_host,
            "sqlserver_db": t.sqlserver_db,
            "sqlserver_user": t.sqlserver_user,
            "sqlserver_driver": t.sqlserver_driver,
            "external_db_configured": t.external_db is not None,
            "external_db_engine": (t.external_db or {}).get("engine"),
            "external_db": (
                {
                    "engine": t.external_db.get("engine", "postgresql"),
                    "host": t.external_db.get("host") or "",
                    "port": t.external_db.get("port") or 5432,
                    "database": t.external_db.get("database") or "",
                    "user": t.external_db.get("user") or "",
                    "schema_description": t.external_db.get("schema_description"),
                }
                if t.external_db
                else None
            ),
            "external_sheets_configured": t.external_sheets is not None,
            "external_sheets_spreadsheet": (t.external_sheets or {}).get("spreadsheet_url", ""),
            "external_sheets": (
                {
                    "spreadsheet_url": t.external_sheets.get("spreadsheet_url", ""),
                    "spreadsheet_id": t.external_sheets.get("spreadsheet_id", ""),
                    "schema_description": t.external_sheets.get("schema_description"),
                }
                if t.external_sheets
                else None
            ),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tenants
    ]


@router.post("/tenants")
async def tenant_create(
    body: TenantCreate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    payload = body.model_dump()

    # Base de datos externa: validar conexión antes de crear el tenant
    ext = payload.get("external_db")
    if ext:
        from mind.data.external.postgresql import test_connection
        creds = {
            "engine": ext.get("engine", "postgresql"),
            "host": ext.get("host", ""),
            "port": ext.get("port", 5432),
            "database": ext.get("database", ""),
            "user": ext.get("user", ""),
            "password": ext.get("password", ""),
        }
        try:
            await asyncio.wait_for(test_connection(creds), timeout=15)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=400,
                detail="No se pudo crear: timeout conectando a la base de datos externa (15 s).",
            ) from None
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"No se pudo crear: error de conexión a la base externa — {exc}",
            ) from exc

    # Google Sheets: validar conexión antes de crear el tenant
    sheets = payload.get("external_sheets")
    if sheets:
        from mind.data.sheets.google_sheets import (
            test_connection as test_sheets_connection,
            _extract_spreadsheet_id,
            _validate_conf,
        )
        conf = dict(sheets)
        sid = _extract_spreadsheet_id(conf.get("spreadsheet_url") or "")
        conf["spreadsheet_id"] = sid
        _validate_conf(conf)
        try:
            await asyncio.wait_for(test_sheets_connection(conf), timeout=15)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=400,
                detail="No se pudo crear: timeout conectando a Google Sheets (15 s).",
            ) from None
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"No se pudo crear: error de conexión a Google Sheets — {exc}",
            ) from exc

    tenant = Tenant(**payload)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    # Inicializar el bot en memoria y registrar webhook
    try:
        from mind.telegram.bot import init_bot, setup_webhook
        bot_app = init_bot(tenant.bot_token)
        await bot_app.initialize()
        await setup_webhook(tenant.webhook_url, tenant.bot_token)
    except Exception as exc:
        logger.warning("No se pudo inicializar bot para nuevo tenant %s: %s", tenant.slug, exc)

    # Recargar caché de tenants
    from mind.tenants.resolver import reload_tenant
    await reload_tenant(tenant.id, session)

    logger.info("Tenant creado: %s por %s", tenant.slug, admin.get("sub"))
    return {"id": tenant.id, "slug": tenant.slug}


@router.put("/tenants/{tenant_id}")
async def tenant_update(
    tenant_id: int,
    body: TenantUpdate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    old_token = tenant.bot_token
    updates = body.model_dump(exclude_none=True)

    # external_db: merge sobre lo almacenado — los campos vacíos conservan
    # los valores guardados (password incluido); engine null desconfigura
    if body.external_db is not None:
        if body.external_db.get("engine") is None:
            tenant.external_db = None
        else:
            stored = tenant.external_db or {}
            merged = dict(stored)
            for key in ("engine", "host", "port", "database", "user", "password", "schema_description"):
                val = body.external_db.get(key)
                if val:
                    merged[key] = int(val) if key == "port" else val
            tenant.external_db = merged
        updates.pop("external_db", None)

    # external_sheets: merge sobre lo almacenado
    if body.external_sheets is not None:
        stored = tenant.external_sheets or {}
        merged = dict(stored)
        url = body.external_sheets.get("spreadsheet_url") or ""
        creds = body.external_sheets.get("credentials")
        schema_desc = body.external_sheets.get("schema_description")

        if not url.strip() and not creds:
            # Si no hay URL y no hay credenciales → desconfigurar
            if not stored.get("spreadsheet_url"):
                tenant.external_sheets = None
        else:
            if url.strip():
                from mind.data.sheets.google_sheets import _extract_spreadsheet_id
                merged["spreadsheet_url"] = url.strip()
                merged["spreadsheet_id"] = _extract_spreadsheet_id(url)
            if creds:
                merged["credentials"] = creds
            elif "credentials" in stored:
                merged["credentials"] = stored["credentials"]
            if schema_desc:
                merged["schema_description"] = schema_desc
            tenant.external_sheets = merged
        updates.pop("external_sheets", None)

    for key, val in updates.items():
        setattr(tenant, key, val)
    await session.commit()

    # Si cambió el token, re-inicializar el bot
    new_token = tenant.bot_token
    if "bot_token" in updates and old_token != new_token:
        from mind.telegram.bot import teardown_bot, init_bot, setup_webhook
        await teardown_bot(old_token)
        bot_app = init_bot(new_token)
        await bot_app.initialize()
        try:
            await setup_webhook(tenant.webhook_url, new_token)
        except Exception as exc:
            logger.warning("No se pudo registrar webhook tras cambio de token tenant %s: %s", tenant.slug, exc)

    # Recargar caché
    from mind.tenants.resolver import reload_tenant
    await reload_tenant(tenant.id, session)

    logger.info("Tenant %s actualizado por %s", tenant.slug, admin.get("sub"))
    return {"ok": True}


@router.delete("/tenants/{tenant_id}")
async def tenant_delete(
    tenant_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    # Apagar el bot antes de eliminar
    from mind.telegram.bot import teardown_bot
    await teardown_bot(tenant.bot_token)

    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
    await session.commit()

    # Limpiar caché
    from mind.tenants import resolver as _res
    _res._token_map.pop(tenant.bot_token, None)
    _res._id_map.pop(tenant_id, None)

    logger.info("Tenant %s eliminado por %s", tenant.slug, admin.get("sub"))
    return {"ok": True}


# ── BASE DE DATOS EXTERNA ────────────────────────────────────────────────────

def _resolve_external_creds(body: ExternalDbPayload, stored: dict | None) -> dict:
    """Combina el body recibido con lo almacenado (password vacío → stored)."""
    creds = body.model_dump()
    if not creds.get("password") and stored:
        creds["password"] = stored.get("password") or ""
    return creds


def _resolve_external_sheets(body: ExternalSheetsPayload, stored: dict | None) -> dict:
    """Combina el body recibido con lo almacenado (credentials vacío → stored)."""
    from mind.data.sheets.google_sheets import _extract_spreadsheet_id
    conf: dict = {}
    url = body.spreadsheet_url.strip()
    if url:
        conf["spreadsheet_url"] = url
        conf["spreadsheet_id"] = _extract_spreadsheet_id(url)
    if body.credentials:
        conf["credentials"] = body.credentials
    elif stored and stored.get("credentials"):
        conf["credentials"] = stored["credentials"]
    if stored and stored.get("schema_description"):
        conf["schema_description"] = stored["schema_description"]
    return conf if conf else {}


@router.post("/tenants/{tenant_id}/test-external-db")
async def tenant_test_external_db(
    tenant_id: int,
    body: ExternalDbPayload,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    creds = _resolve_external_creds(body, tenant.external_db)
    from mind.data.external.postgresql import test_connection
    try:
        await asyncio.wait_for(test_connection(creds), timeout=15)
        return {"ok": True}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout conectando a la base de datos externa (15 s)."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/tenants/{tenant_id}/discover-schema")
async def tenant_discover_schema(
    tenant_id: int,
    body: ExternalDbPayload,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    creds = _resolve_external_creds(body, tenant.external_db)
    from mind.data.external.schema_discovery import (
        introspect_schema,
        generate_schema_description,
    )

    async def _discover() -> tuple[str | None, bool]:
        raw = await introspect_schema(creds)
        if not raw:
            return None, True
        return (await generate_schema_description(raw)), False

    try:
        description, empty = await asyncio.wait_for(_discover(), timeout=90)
        if empty:
            return {"schema_description": "", "empty": True}
        return {"schema_description": description}
    except asyncio.TimeoutError:
        return {"error": "Timeout del descubrimiento de esquema (90 s)."}
    except Exception as exc:
        return {"error": str(exc)}


# ── GOOGLE SHEETS EXTERNA ──────────────────────────────────────────────────────

@router.post("/tenants/{tenant_id}/test-sheets")
async def tenant_test_sheets(
    tenant_id: int,
    body: ExternalSheetsPayload,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    conf = _resolve_external_sheets(body, tenant.external_sheets)
    from mind.data.sheets.google_sheets import test_connection, _validate_conf
    try:
        _validate_conf(conf)
        sheets = await asyncio.wait_for(test_connection(conf), timeout=15)
        return {"ok": True, "sheets": sheets}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout conectando a Google Sheets (15 s)."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/tenants/{tenant_id}/discover-sheets")
async def tenant_discover_sheets(
    tenant_id: int,
    body: ExternalSheetsPayload,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    conf = _resolve_external_sheets(body, tenant.external_sheets)

    from mind.data.sheets.google_sheets import _validate_conf
    from mind.data.sheets.schema_discovery import (
        introspect_sheets,
        generate_sheets_description,
    )

    try:
        _validate_conf(conf)
        raw = await asyncio.wait_for(introspect_sheets(conf), timeout=30)
        if not raw:
            return {"sheets": [], "schema_description": "", "empty": True}
        description = await asyncio.wait_for(
            generate_sheets_description(raw), timeout=60
        )
        return {
            "schema_description": description,
            "sheets": raw,
        }
    except asyncio.TimeoutError:
        return {"error": "Timeout del descubrimiento de hojas (90 s)."}
    except Exception as exc:
        return {"error": str(exc)}


# ── DASHBOARD ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import User, AuditLog, AccessRequest, ScheduledTask, Tenant

    def _where(stmt, model):
        if tenant_id:
            return stmt.where(model.tenant_id == tenant_id)
        return stmt

    total_users = (await session.execute(
        _where(select(sqlfunc.count()).select_from(User), User)
    )).scalar()
    pending_requests = (await session.execute(
        _where(
            select(sqlfunc.count()).select_from(AccessRequest)
            .where(AccessRequest.status == "pending"),
            AccessRequest,
        )
    )).scalar()
    total_interactions = (await session.execute(
        _where(
            select(sqlfunc.count()).select_from(AuditLog)
            .where(AuditLog.event_type == "interaction"),
            AuditLog,
        )
    )).scalar()
    active_tasks = (await session.execute(
        _where(
            select(sqlfunc.count()).select_from(ScheduledTask)
            .where(ScheduledTask.status == "active"),
            ScheduledTask,
        )
    )).scalar()
    errors_today = (await session.execute(
        _where(
            select(sqlfunc.count()).select_from(AuditLog)
            .where(AuditLog.status == "error"),
            AuditLog,
        )
    )).scalar()

    logs_stmt = select(AuditLog).order_by(AuditLog.timestamp_utc.desc()).limit(10)
    if tenant_id:
        logs_stmt = logs_stmt.where(AuditLog.tenant_id == tenant_id)
    recent_logs = (await session.execute(logs_stmt)).scalars().all()

    return {
        "stats": {
            "total_users": total_users,
            "pending_requests": pending_requests,
            "total_interactions": total_interactions,
            "active_tasks": active_tasks,
            "errors_today": errors_today,
        },
        "recent_logs": [
            {
                "id": log.id,
                "tenant_id": log.tenant_id,
                "event_type": log.event_type,
                "chat_id": log.chat_id,
                "request_content": (log.request_content or "")[:100],
                "status": log.status,
                "timestamp_utc": log.timestamp_utc.isoformat() if log.timestamp_utc else None,
                "tool_invoked": log.tool_invoked,
            }
            for log in recent_logs
        ],
    }


# ── AGENTE ───────────────────────────────────────────────────────────────────

@router.get("/agente")
async def agente_get(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import AgentConfig
    cfg = (await session.execute(
        select(AgentConfig).where(AgentConfig.tenant_id == tenant_id).limit(1)
    )).scalar_one_or_none()
    if not cfg:
        return {
            "system_prompt": "",
            "model": "openai/gpt-4o-mini",
            "temperature": 0.7,
            "conversation_window": 20,
            "max_tool_cycles": 5,
            "updated_at": None,
        }
    return {
        "system_prompt": cfg.system_prompt,
        "model": cfg.model,
        "temperature": cfg.temperature,
        "conversation_window": cfg.conversation_window,
        "max_tool_cycles": cfg.max_tool_cycles,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.put("/agente")
async def agente_update(
    body: AgentConfigUpdate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import AgentConfig
    cfg = (await session.execute(
        select(AgentConfig).where(AgentConfig.tenant_id == tenant_id).limit(1)
    )).scalar_one_or_none()
    if cfg:
        cfg.system_prompt = body.system_prompt
        cfg.model = body.model
        cfg.temperature = max(0.0, min(2.0, body.temperature))
        cfg.conversation_window = max(1, min(100, body.conversation_window))
        cfg.max_tool_cycles = max(1, min(20, body.max_tool_cycles))
    else:
        session.add(AgentConfig(tenant_id=tenant_id, **body.model_dump()))
    await session.commit()
    logger.info("AgentConfig tenant_id=%s actualizado por %s", tenant_id, admin.get("sub"))
    return {"ok": True}


# ── USUARIOS ─────────────────────────────────────────────────────────────────

@router.get("/usuarios")
async def usuarios_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import User, Role
    users = (await session.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.created_at.desc())
    )).scalars().all()
    roles_map = {
        r.id: r.name
        for r in (await session.execute(
            select(Role).where(Role.tenant_id == tenant_id)
        )).scalars().all()
    }
    return [
        {
            "chat_id": u.chat_id,
            "user_id": u.user_id,
            "username": u.username,
            "role_id": u.role_id,
            "role_name": roles_map.get(u.role_id, "—"),
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.patch("/usuarios/{chat_id}/toggle")
async def usuario_toggle(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import User
    user = (await session.execute(
        select(User).where(User.chat_id == chat_id, User.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.is_active = not user.is_active
    await session.commit()
    return {"chat_id": chat_id, "is_active": user.is_active}


@router.patch("/usuarios/{chat_id}/rol")
async def usuario_cambiar_rol(
    chat_id: int,
    body: dict,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import User
    user = (await session.execute(
        select(User).where(User.chat_id == chat_id, User.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.role_id = body["role_id"]
    await session.commit()
    return {"ok": True}


@router.delete("/usuarios/{chat_id}")
async def usuario_eliminar(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import User
    await session.execute(
        delete(User).where(User.chat_id == chat_id, User.tenant_id == tenant_id)
    )
    await session.commit()
    return {"ok": True}


# ── ACCESOS ──────────────────────────────────────────────────────────────────

@router.get("/accesos")
async def accesos_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import AccessRequest
    reqs = (await session.execute(
        select(AccessRequest)
        .where(AccessRequest.tenant_id == tenant_id)
        .order_by(AccessRequest.created_at.desc())
    )).scalars().all()
    return [
        {
            "id": r.id,
            "chat_id": r.chat_id,
            "user_id": r.user_id,
            "username": r.username,
            "first_name": r.first_name,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reqs
    ]


@router.post("/accesos/{chat_id}/aprobar")
async def acceso_aprobar(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.auth.access_requests import approve_user
    user = await approve_user(chat_id, tenant_id, session)
    await session.commit()
    if not user:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada o ya procesada")
    return {"ok": True}


@router.post("/accesos/{chat_id}/rechazar")
async def acceso_rechazar(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.auth.access_requests import reject_request
    ok = await reject_request(chat_id, tenant_id, session)
    await session.commit()
    return {"ok": ok}


# ── ROLES ────────────────────────────────────────────────────────────────────

@router.get("/roles")
async def roles_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import Role, RolePermission
    roles = (await session.execute(
        select(Role).where(Role.tenant_id == tenant_id)
    )).scalars().all()
    perms = (await session.execute(select(RolePermission))).scalars().all()
    perms_by_role: dict[int, list[str]] = {}
    for p in perms:
        perms_by_role.setdefault(p.role_id, []).append(p.permission_name)
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "permissions": perms_by_role.get(r.id, []),
        }
        for r in roles
    ]


@router.put("/roles/{role_id}/permisos")
async def rol_actualizar_permisos(
    role_id: int,
    body: RolePermissionsUpdate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import RolePermission
    from mind.auth.authorization import Permission, _invalidate_permissions_cache
    valid = {p.value for p in Permission}
    await session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    for perm in body.permissions:
        if perm in valid:
            session.add(RolePermission(role_id=role_id, permission_name=perm))
    await session.commit()
    _invalidate_permissions_cache()
    return {"ok": True}


@router.post("/roles")
async def rol_crear(
    body: NewRole,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Role
    role = Role(name=body.name, description=body.description, tenant_id=body.tenant_id)
    session.add(role)
    await session.commit()
    return {"id": role.id, "name": role.name}


# ── HISTORIAL ────────────────────────────────────────────────────────────────

@router.get("/historial")
async def historial_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
    chat_id: int | None = None,
):
    from mind.db.models import ConversationMessage, User
    users = (await session.execute(
        select(User).where(User.tenant_id == tenant_id, User.is_active == True)
    )).scalars().all()

    messages = []
    if chat_id:
        msgs = (await session.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.chat_id == chat_id,
                ConversationMessage.tenant_id == tenant_id,
            )
            .order_by(ConversationMessage.created_at.asc())
            .limit(200)
        )).scalars().all()
        messages = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_name": m.tool_name,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ]

    return {
        "users": [
            {"chat_id": u.chat_id, "username": u.username, "user_id": u.user_id}
            for u in users
        ],
        "messages": messages,
    }


@router.delete("/historial/{chat_id}")
async def historial_limpiar(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import ConversationMessage
    await session.execute(
        delete(ConversationMessage).where(
            ConversationMessage.chat_id == chat_id,
            ConversationMessage.tenant_id == tenant_id,
        )
    )
    await session.commit()
    return {"ok": True}


# ── AUDITORÍA ────────────────────────────────────────────────────────────────

@router.get("/auditoria")
async def auditoria_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
    event_type: str = "",
    status_filter: str = "",
    limit: int = 100,
):
    from mind.db.models import AuditLog
    stmt = select(AuditLog).order_by(AuditLog.timestamp_utc.desc())
    if tenant_id:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)
    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)
    if status_filter:
        stmt = stmt.where(AuditLog.status == status_filter)
    stmt = stmt.limit(min(limit, 500))
    logs = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": log.id,
            "tenant_id": log.tenant_id,
            "event_type": log.event_type,
            "timestamp_utc": log.timestamp_utc.isoformat() if log.timestamp_utc else None,
            "chat_id": log.chat_id,
            "request_content": (log.request_content or "")[:200],
            "tool_invoked": log.tool_invoked,
            "status": log.status,
            "error_description": log.error_description,
        }
        for log in logs
    ]


# ── TAREAS ───────────────────────────────────────────────────────────────────

@router.get("/tareas")
async def tareas_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int = Query(...),
):
    from mind.db.models import ScheduledTask
    tasks = (await session.execute(
        select(ScheduledTask)
        .where(ScheduledTask.tenant_id == tenant_id)
        .order_by(ScheduledTask.created_at.desc())
    )).scalars().all()
    return [
        {
            "id": t.id,
            "chat_id": t.chat_id,
            "description": t.description,
            "cron_expression": t.cron_expression,
            "timezone": t.timezone,
            "status": t.status,
            "last_execution_at": t.last_execution_at.isoformat() if t.last_execution_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


@router.patch("/tareas/{task_id}/toggle")
async def tarea_toggle(
    task_id: str,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import ScheduledTask
    task = (await session.execute(
        select(ScheduledTask).where(ScheduledTask.id == task_id)
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    task.status = "inactive" if task.status == "active" else "active"
    await session.commit()
    return {"id": task_id, "status": task.status}


@router.delete("/tareas/{task_id}")
async def tarea_eliminar(
    task_id: str,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import ScheduledTask
    await session.execute(delete(ScheduledTask).where(ScheduledTask.id == task_id))
    await session.commit()
    return {"ok": True}
