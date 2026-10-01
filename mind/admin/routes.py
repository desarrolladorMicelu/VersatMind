"""
API REST del panel de administración — /api/admin/*
Multi-tenant: los endpoints de datos aceptan ?tenant_id= para filtrar.
- superadmin: puede ver todos los tenants, pasa tenant_id como query param
- tenant_admin: solo ve su tenant, el tenant_id viene del JWT
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import (
    create_access_token, require_admin, require_superadmin,
    verify_superadmin, get_effective_tenant_id,
    hash_password, verify_password,
)
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
    external_alegra: dict | None = None
    report_config: dict | None = None

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
    external_alegra: dict | None = None
    report_config: dict | None = None

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

class TenantAdminCreate(BaseModel):
    username: str
    password: str

class TenantAdminUpdate(BaseModel):
    password: str | None = None
    is_active: bool | None = None

class UsageSettingsUpdate(BaseModel):
    threshold_usd: float = 8.0
    period: str = "month"          # "month" | "total"
    auto_pause: bool = False
    notify_telegram: bool = True
    notify_email: bool = False
    admin_email: str | None = None

class UsagePauseRequest(BaseModel):
    reason: str | None = None

class ScheduledPromptCreate(BaseModel):
    name: str
    description: str = ""
    prompt: str
    chat_id: int
    chat_label: str = ""
    send_to_all: bool = False
    frequency: str = "daily"          # "daily" | "weekly" | "custom"
    hour: int = 8
    minute: int = 0
    weekday: int = 0                  # 0 = lunes ... 6 = domingo
    cron_expression: str | None = None  # requerido si frequency = "custom"
    timezone: str = "America/Bogota"
    is_active: bool = True

class ScheduledPromptUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt: str | None = None
    chat_id: int | None = None
    chat_label: str | None = None
    send_to_all: bool | None = None
    frequency: str | None = None
    hour: int | None = None
    minute: int | None = None
    weekday: int | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    is_active: bool | None = None

class KnowledgeCreate(BaseModel):
    title: str
    content: str
    source: str = ""
    tags: str = ""

class KnowledgeUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    source: str | None = None
    tags: str | None = None
    is_active: bool | None = None

class PromptPreviewRequest(BaseModel):
    prompt: str


# ── AUTH ─────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """
    Login unificado:
    1. Superadmin (.env) → acceso a todos los tenants
    2. TenantAdmin (BD)  → acceso solo a su tenant
    """
    # 1. Superadmin
    if verify_superadmin(body.username, body.password):
        token = create_access_token(body.username, role="superadmin")
        response.set_cookie(
            "admin_token", token,
            httponly=True, samesite="lax",
            max_age=86400, path="/",
        )
        return {"token": token, "username": body.username, "role": "superadmin", "tenant_id": None}

    # 2. Tenant admin
    from mind.db.models import TenantAdmin

    result = await session.execute(
        select(TenantAdmin).where(
            TenantAdmin.username == body.username,
            TenantAdmin.is_active.is_(True),
        )
    )
    ta = result.scalar_one_or_none()
    if ta is None or not verify_password(body.password, ta.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    token = create_access_token(body.username, role="tenant_admin", tenant_id=ta.tenant_id)
    response.set_cookie(
        "admin_token", token,
        httponly=True, samesite="lax",
        max_age=86400, path="/",
    )
    return {"token": token, "username": body.username, "role": "tenant_admin", "tenant_id": ta.tenant_id}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("admin_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(admin=Depends(require_admin)):
    return {
        "username": admin.get("sub"),
        "role": admin.get("role", "superadmin"),
        "tenant_id": admin.get("tenant_id"),
    }


# ── TENANT ADMINS (solo superadmin puede gestionarlos) ───────────────────────

@router.get("/tenants/{tenant_id}/admins")
async def tenant_admins_list(
    tenant_id: int,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import TenantAdmin
    admins = (await session.execute(
        select(TenantAdmin).where(TenantAdmin.tenant_id == tenant_id)
    )).scalars().all()
    return [
        {
            "id": a.id,
            "username": a.username,
            "is_active": a.is_active,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in admins
    ]


@router.post("/tenants/{tenant_id}/admins")
async def tenant_admin_create(
    tenant_id: int,
    body: TenantAdminCreate,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import TenantAdmin

    # Verificar que el tenant existe
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    # Verificar username único dentro del tenant
    existing = (await session.execute(
        select(TenantAdmin).where(
            TenantAdmin.tenant_id == tenant_id,
            TenantAdmin.username == body.username,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Ya existe un admin con ese username en este tenant")

    ta = TenantAdmin(
        tenant_id=tenant_id,
        username=body.username,
        password_hash=hash_password(body.password),
        is_active=True,
    )
    session.add(ta)
    await session.commit()
    await session.refresh(ta)
    return {"id": ta.id, "username": ta.username}


@router.patch("/tenants/{tenant_id}/admins/{admin_id}")
async def tenant_admin_update(
    tenant_id: int,
    admin_id: int,
    body: TenantAdminUpdate,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import TenantAdmin

    ta = (await session.execute(
        select(TenantAdmin).where(
            TenantAdmin.id == admin_id,
            TenantAdmin.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if not ta:
        raise HTTPException(status_code=404, detail="Admin no encontrado")

    if body.password:
        ta.password_hash = hash_password(body.password)
    if body.is_active is not None:
        ta.is_active = body.is_active
    await session.commit()
    return {"ok": True}


@router.delete("/tenants/{tenant_id}/admins/{admin_id}")
async def tenant_admin_delete(
    tenant_id: int,
    admin_id: int,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import TenantAdmin
    await session.execute(
        delete(TenantAdmin).where(
            TenantAdmin.id == admin_id,
            TenantAdmin.tenant_id == tenant_id,
        )
    )
    await session.commit()
    return {"ok": True}


# ── TENANTS (solo superadmin) ─────────────────────────────────────────────────

@router.get("/tenants")
async def tenants_list(
    admin=Depends(require_superadmin),
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
            "external_alegra_configured": t.external_alegra is not None,
            "external_alegra": (
                {
                    "email": t.external_alegra.get("email", ""),
                    "schema_description": t.external_alegra.get("schema_description"),
                }
                if t.external_alegra
                else None
            ),
            "report_config_configured": t.report_config is not None,
            "report_config": (
                {
                    "company_name": t.report_config.get("company_name", ""),
                    "sections": t.report_config.get("sections", []),
                    "additional_instructions": t.report_config.get("additional_instructions"),
                }
                if t.report_config
                else None
            ),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tenants
    ]


@router.post("/tenants")
async def tenant_create(
    body: TenantCreate,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = Tenant(**body.model_dump())
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    # Validar conexion externa si se proporcionó
    ext = body.external_db
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

    sheets = body.external_sheets
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

    try:
        from mind.telegram.bot import init_bot, setup_webhook
        bot_app = init_bot(tenant.bot_token)
        await bot_app.initialize()
        await setup_webhook(tenant.webhook_url, tenant.bot_token)
    except Exception as exc:
        logger.warning("No se pudo inicializar bot para nuevo tenant %s: %s", tenant.slug, exc)

    from mind.tenants.resolver import reload_tenant
    await reload_tenant(tenant.id, session)

    logger.info("Tenant creado: %s por %s", tenant.slug, admin.get("sub"))
    return {"id": tenant.id, "slug": tenant.slug}


@router.put("/tenants/{tenant_id}")
async def tenant_update(
    tenant_id: int,
    body: TenantUpdate,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    old_token = tenant.bot_token
    updates = body.model_dump(exclude_none=True, exclude={"external_db", "external_sheets", "external_alegra", "report_config"})
    for key, val in updates.items():
        setattr(tenant, key, val)

    # external_db: merge sobre lo almacenado
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

    # external_sheets: merge sobre lo almacenado
    if body.external_sheets is not None:
        stored = tenant.external_sheets or {}
        merged = dict(stored)
        url = body.external_sheets.get("spreadsheet_url") or ""
        creds = body.external_sheets.get("credentials")
        schema_desc = body.external_sheets.get("schema_description")
        if not url.strip() and not creds:
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

    # external_alegra: merge sobre lo almacenado
    if body.external_alegra is not None:
        stored = tenant.external_alegra or {}
        merged = dict(stored)
        email_val = body.external_alegra.get("email") or ""
        token_val = body.external_alegra.get("token") or ""
        schema_desc = body.external_alegra.get("schema_description")
        groups = body.external_alegra.get("groups")

        if not email_val.strip() and not token_val.strip():
            if not stored.get("email"):
                tenant.external_alegra = None
        else:
            if email_val.strip():
                merged["email"] = email_val.strip()
            elif "email" in stored:
                merged["email"] = stored["email"]
            if token_val.strip():
                merged["token"] = token_val.strip()
            elif "token" in stored:
                merged["token"] = stored["token"]
            if groups:
                merged["groups"] = groups
            elif "groups" in stored:
                merged["groups"] = stored["groups"]
            if schema_desc:
                merged["schema_description"] = schema_desc
            tenant.external_alegra = merged

    # report_config: merge sobre lo almacenado
    if body.report_config is not None:
        stored = tenant.report_config or {}
        merged = dict(stored)
        for k in ("company_name", "company_logo", "sections", "additional_instructions", "template_style"):
            v = body.report_config.get(k)
            if v is not None:
                merged[k] = v
        tenant.report_config = merged if merged else None

    await session.commit()

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

    from mind.tenants.resolver import reload_tenant
    await reload_tenant(tenant.id, session)

    logger.info("Tenant %s actualizado por %s", tenant.slug, admin.get("sub"))
    return {"ok": True}


@router.delete("/tenants/{tenant_id}")
async def tenant_delete(
    tenant_id: int,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    from mind.telegram.bot import teardown_bot
    await teardown_bot(tenant.bot_token)

    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
    await session.commit()

    from mind.tenants import resolver as _res
    _res._token_map.pop(tenant.bot_token, None)
    _res._id_map.pop(tenant_id, None)

    logger.info("Tenant %s eliminado por %s", tenant.slug, admin.get("sub"))
    return {"ok": True}


# ── EXTERNAL DB & SHEETS ─────────────────────────────────────────────────────

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
        tables = await asyncio.wait_for(test_connection(creds), timeout=15)
        return {"ok": True, "tables": tables}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout conectando a la base externa (15 s)."}
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


# ── ALEGRA MCP ──────────────────────────────────────────────────────────────

@router.post("/tenants/{tenant_id}/alegra/test")
async def tenant_test_alegra(
    tenant_id: int,
    body: dict,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    stored = (tenant.external_alegra or {}) if tenant.external_alegra else {}
    conf = {
        "email": body.get("email") or stored.get("email", ""),
        "token": body.get("token") or stored.get("token", ""),
        "groups": body.get("groups") or stored.get("groups"),
    }
    from mind.data.alegra.alegra_mcp import test_connection, AlegraError
    try:
        tools = await asyncio.wait_for(test_connection(conf), timeout=20)
        return {"ok": True, "tools_count": len(tools)}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout conectando a Alegra (20 s)."}
    except AlegraError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/tenants/{tenant_id}/alegra/discover")
async def tenant_discover_alegra(
    tenant_id: int,
    body: dict,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Tenant
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    stored = (tenant.external_alegra or {}) if tenant.external_alegra else {}
    conf = {
        "email": body.get("email") or stored.get("email", ""),
        "token": body.get("token") or stored.get("token", ""),
        "groups": body.get("groups") or stored.get("groups"),
    }
    from mind.data.alegra.alegra_mcp import generate_description, AlegraError
    try:
        description = await asyncio.wait_for(generate_description(conf), timeout=30)
        return {"schema_description": description}
    except asyncio.TimeoutError:
        return {"error": "Timeout descubriendo tools de Alegra (30 s)."}
    except AlegraError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import User, AuditLog, AccessRequest, ScheduledTask
    tid = get_effective_tenant_id(admin, tenant_id) if tenant_id or admin.get("role") == "tenant_admin" else None

    def _where(stmt, model):
        if tid:
            return stmt.where(model.tenant_id == tid)
        return stmt

    total_users = (await session.execute(_where(select(sqlfunc.count()).select_from(User), User))).scalar()
    pending_requests = (await session.execute(
        _where(select(sqlfunc.count()).select_from(AccessRequest).where(AccessRequest.status == "pending"), AccessRequest)
    )).scalar()
    total_interactions = (await session.execute(
        _where(select(sqlfunc.count()).select_from(AuditLog).where(AuditLog.event_type == "interaction"), AuditLog)
    )).scalar()
    active_tasks = (await session.execute(
        _where(select(sqlfunc.count()).select_from(ScheduledTask).where(ScheduledTask.status == "active"), ScheduledTask)
    )).scalar()
    errors_today = (await session.execute(
        _where(select(sqlfunc.count()).select_from(AuditLog).where(AuditLog.status == "error"), AuditLog)
    )).scalar()

    logs_stmt = select(AuditLog).order_by(AuditLog.timestamp_utc.desc()).limit(10)
    if tid:
        logs_stmt = logs_stmt.where(AuditLog.tenant_id == tid)
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


# ── AGENTE ────────────────────────────────────────────────────────────────────

@router.get("/agente")
async def agente_get(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import AgentConfig
    tid = get_effective_tenant_id(admin, tenant_id)
    cfg = (await session.execute(
        select(AgentConfig).where(AgentConfig.tenant_id == tid).limit(1)
    )).scalar_one_or_none()
    if not cfg:
        return {"system_prompt": "", "model": "openai/gpt-4o-mini", "temperature": 0.7,
                "conversation_window": 20, "max_tool_cycles": 5, "updated_at": None}
    return {
        "system_prompt": cfg.system_prompt, "model": cfg.model,
        "temperature": cfg.temperature, "conversation_window": cfg.conversation_window,
        "max_tool_cycles": cfg.max_tool_cycles,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.put("/agente")
async def agente_update(
    body: AgentConfigUpdate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import AgentConfig
    tid = get_effective_tenant_id(admin, tenant_id)
    cfg = (await session.execute(
        select(AgentConfig).where(AgentConfig.tenant_id == tid).limit(1)
    )).scalar_one_or_none()
    if cfg:
        cfg.system_prompt = body.system_prompt
        cfg.model = body.model
        cfg.temperature = max(0.0, min(2.0, body.temperature))
        cfg.conversation_window = max(1, min(100, body.conversation_window))
        cfg.max_tool_cycles = max(1, min(20, body.max_tool_cycles))
    else:
        session.add(AgentConfig(tenant_id=tid, **body.model_dump()))
    await session.commit()
    return {"ok": True}


# ── USUARIOS ──────────────────────────────────────────────────────────────────

@router.get("/usuarios")
async def usuarios_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import User, Role
    tid = get_effective_tenant_id(admin, tenant_id)
    users = (await session.execute(
        select(User).where(User.tenant_id == tid).order_by(User.created_at.desc())
    )).scalars().all()
    roles_map = {
        r.id: r.name for r in (await session.execute(
            select(Role).where(Role.tenant_id == tid)
        )).scalars().all()
    }
    return [
        {"chat_id": u.chat_id, "user_id": u.user_id, "username": u.username,
         "role_id": u.role_id, "role_name": roles_map.get(u.role_id, "—"),
         "is_active": u.is_active,
         "created_at": u.created_at.isoformat() if u.created_at else None}
        for u in users
    ]


@router.patch("/usuarios/{chat_id}/toggle")
async def usuario_toggle(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import User
    tid = get_effective_tenant_id(admin, tenant_id)
    user = (await session.execute(
        select(User).where(User.chat_id == chat_id, User.tenant_id == tid)
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
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import User
    tid = get_effective_tenant_id(admin, tenant_id)
    user = (await session.execute(
        select(User).where(User.chat_id == chat_id, User.tenant_id == tid)
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
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import User
    tid = get_effective_tenant_id(admin, tenant_id)
    await session.execute(delete(User).where(User.chat_id == chat_id, User.tenant_id == tid))
    await session.commit()
    return {"ok": True}


# ── ACCESOS ───────────────────────────────────────────────────────────────────

@router.get("/accesos")
async def accesos_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import AccessRequest
    tid = get_effective_tenant_id(admin, tenant_id)
    reqs = (await session.execute(
        select(AccessRequest).where(AccessRequest.tenant_id == tid).order_by(AccessRequest.created_at.desc())
    )).scalars().all()
    return [
        {"id": r.id, "chat_id": r.chat_id, "user_id": r.user_id,
         "username": r.username, "first_name": r.first_name, "status": r.status,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in reqs
    ]


@router.post("/accesos/{chat_id}/aprobar")
async def acceso_aprobar(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.auth.access_requests import approve_user
    tid = get_effective_tenant_id(admin, tenant_id)
    user = await approve_user(chat_id, tid, session)
    await session.commit()
    if not user:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada o ya procesada")
    return {"ok": True}


@router.post("/accesos/{chat_id}/rechazar")
async def acceso_rechazar(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.auth.access_requests import reject_request
    tid = get_effective_tenant_id(admin, tenant_id)
    ok = await reject_request(chat_id, tid, session)
    await session.commit()
    return {"ok": ok}


# ── ROLES ─────────────────────────────────────────────────────────────────────

@router.get("/roles")
async def roles_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import Role, RolePermission
    tid = get_effective_tenant_id(admin, tenant_id)
    roles = (await session.execute(select(Role).where(Role.tenant_id == tid))).scalars().all()
    perms = (await session.execute(select(RolePermission))).scalars().all()
    perms_by_role: dict[int, list[str]] = {}
    for p in perms:
        perms_by_role.setdefault(p.role_id, []).append(p.permission_name)
    return [
        {"id": r.id, "name": r.name, "description": r.description,
         "permissions": perms_by_role.get(r.id, [])}
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
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import Role
    tid = get_effective_tenant_id(admin, tenant_id)
    role = Role(name=body.name, description=body.description, tenant_id=tid)
    session.add(role)
    await session.commit()
    return {"id": role.id, "name": role.name}


# ── HISTORIAL ─────────────────────────────────────────────────────────────────

@router.get("/historial")
async def historial_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
    chat_id: int | None = None,
):
    from mind.db.models import ConversationMessage, User
    tid = get_effective_tenant_id(admin, tenant_id)
    users = (await session.execute(
        select(User).where(User.tenant_id == tid, User.is_active.is_(True))
    )).scalars().all()

    messages = []
    if chat_id:
        msgs = (await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.chat_id == chat_id, ConversationMessage.tenant_id == tid)
            .order_by(ConversationMessage.created_at.asc()).limit(200)
        )).scalars().all()
        messages = [
            {"id": m.id, "role": m.role, "content": m.content, "tool_name": m.tool_name,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in msgs
        ]
    return {
        "users": [{"chat_id": u.chat_id, "username": u.username, "user_id": u.user_id} for u in users],
        "messages": messages,
    }


@router.delete("/historial/{chat_id}")
async def historial_limpiar(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import ConversationMessage
    tid = get_effective_tenant_id(admin, tenant_id)
    await session.execute(
        delete(ConversationMessage).where(
            ConversationMessage.chat_id == chat_id, ConversationMessage.tenant_id == tid
        )
    )
    await session.commit()
    return {"ok": True}


# ── AUDITORÍA ─────────────────────────────────────────────────────────────────

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
    tid = admin.get("tenant_id") if admin.get("role") == "tenant_admin" else tenant_id
    stmt = select(AuditLog).order_by(AuditLog.timestamp_utc.desc())
    if tid:
        stmt = stmt.where(AuditLog.tenant_id == tid)
    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)
    if status_filter:
        stmt = stmt.where(AuditLog.status == status_filter)
    stmt = stmt.limit(min(limit, 500))
    logs = (await session.execute(stmt)).scalars().all()
    return [
        {"id": log.id, "tenant_id": log.tenant_id, "event_type": log.event_type,
         "timestamp_utc": log.timestamp_utc.isoformat() if log.timestamp_utc else None,
         "chat_id": log.chat_id, "request_content": (log.request_content or "")[:200],
         "tool_invoked": log.tool_invoked, "status": log.status,
         "error_description": log.error_description}
        for log in logs
    ]


# ── TAREAS ────────────────────────────────────────────────────────────────────

@router.get("/tareas")
async def tareas_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import ScheduledTask
    tid = get_effective_tenant_id(admin, tenant_id)
    tasks = (await session.execute(
        select(ScheduledTask).where(ScheduledTask.tenant_id == tid).order_by(ScheduledTask.created_at.desc())
    )).scalars().all()
    return [
        {"id": t.id, "chat_id": t.chat_id, "description": t.description,
         "cron_expression": t.cron_expression, "timezone": t.timezone,
         "status": t.status,
         "last_execution_at": t.last_execution_at.isoformat() if t.last_execution_at else None,
         "created_at": t.created_at.isoformat() if t.created_at else None}
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


# ── CONSUMO DE TOKENS ─────────────────────────────────────────────────────────

def _parse_dt(value: str | None, *, end: bool = False) -> datetime | None:
    """Parsea 'YYYY-MM-DD' o ISO 8601 a datetime UTC. end=True suma un día."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if end and len(value.strip()) <= 10:
        dt = dt + timedelta(days=1)
    return dt


@router.get("/consumo/config")
async def consumo_config_get(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.usage.tracker import get_usage_settings
    tid = get_effective_tenant_id(admin, tenant_id)
    conf = await get_usage_settings(session, tid)
    return {
        "tenant_id": tid,
        "threshold_usd": conf.threshold_usd,
        "period": conf.period,
        "auto_pause": conf.auto_pause,
        "notify_telegram": conf.notify_telegram,
        "notify_email": conf.notify_email,
        "admin_email": conf.admin_email,
    }


@router.put("/consumo/config")
async def consumo_config_update(
    body: UsageSettingsUpdate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import UsageSettings
    tid = get_effective_tenant_id(admin, tenant_id)
    period = body.period if body.period in ("month", "total") else "month"
    threshold = max(0.0, float(body.threshold_usd))

    row = (await session.execute(
        select(UsageSettings).where(UsageSettings.tenant_id == tid).limit(1)
    )).scalar_one_or_none()
    if row is None:
        row = UsageSettings(tenant_id=tid)
        session.add(row)

    row.threshold_usd = threshold
    row.period = period
    row.auto_pause = body.auto_pause
    row.notify_telegram = body.notify_telegram
    row.notify_email = body.notify_email
    row.admin_email = (body.admin_email or "").strip() or None
    await session.commit()
    return {"ok": True}


@router.get("/consumo/global")
async def consumo_global(
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Resumen de consumo por cliente (solo superadmin). Nueva sección."""
    from mind.db.models import Tenant, TokenUsage, UsageSettings, User
    from mind.usage.tracker import get_usage_settings

    start = _parse_dt(date_from)
    end = _parse_dt(date_to, end=True)

    stmt = select(
        TokenUsage.tenant_id,
        TokenUsage.chat_id,
        sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0.0),
        sqlfunc.coalesce(sqlfunc.sum(TokenUsage.total_tokens), 0),
    ).group_by(TokenUsage.tenant_id, TokenUsage.chat_id)
    if start is not None:
        stmt = stmt.where(TokenUsage.created_at >= start)
    if end is not None:
        stmt = stmt.where(TokenUsage.created_at < end)
    per_user = (await session.execute(stmt)).all()

    tenants = (await session.execute(select(Tenant).order_by(Tenant.name))).scalars().all()

    # Umbral por tenant (con default global)
    thresholds: dict[int, float] = {}
    for t in tenants:
        conf = await get_usage_settings(session, t.id)
        thresholds[t.id] = conf.threshold_usd

    paused_rows = (await session.execute(
        select(User.tenant_id, sqlfunc.count()).where(User.is_paused.is_(True)).group_by(User.tenant_id)
    )).all()
    paused_map = {tid: int(cnt) for tid, cnt in paused_rows}

    agg: dict[int, dict] = {
        t.id: {
            "tenant_id": t.id, "name": t.name, "slug": t.slug, "is_active": t.is_active,
            "total_tokens": 0, "total_cost_usd": 0.0, "users_count": 0,
            "over_threshold_count": 0, "paused_count": paused_map.get(t.id, 0),
            "threshold_usd": thresholds.get(t.id, 8.0),
        }
        for t in tenants
    }

    for tenant_id_v, _chat_id, cost, tokens in per_user:
        entry = agg.get(tenant_id_v)
        if entry is None:
            continue
        cost = float(cost or 0.0)
        entry["total_tokens"] += int(tokens or 0)
        entry["total_cost_usd"] += cost
        entry["users_count"] += 1
        if cost >= entry["threshold_usd"] > 0:
            entry["over_threshold_count"] += 1

    rows = sorted(agg.values(), key=lambda r: r["total_cost_usd"], reverse=True)
    for r in rows:
        r["total_cost_usd"] = round(r["total_cost_usd"], 4)

    return {
        "currency": "USD",
        "totals": {
            "total_cost_usd": round(sum(r["total_cost_usd"] for r in rows), 4),
            "total_tokens": sum(r["total_tokens"] for r in rows),
            "tenants_count": len(rows),
            "over_threshold_count": sum(r["over_threshold_count"] for r in rows),
        },
        "tenants": rows,
    }


@router.get("/consumo/usuarios")
async def consumo_usuarios(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Consumo desglosado por usuario dentro de un cliente."""
    from mind.db.models import Role, TokenUsage, UsageAlert, User
    from mind.usage.tracker import get_usage_settings

    tid = get_effective_tenant_id(admin, tenant_id)
    start = _parse_dt(date_from)
    end = _parse_dt(date_to, end=True)
    conf = await get_usage_settings(session, tid)

    stmt = (
        select(
            TokenUsage.chat_id,
            sqlfunc.coalesce(sqlfunc.sum(TokenUsage.prompt_tokens), 0),
            sqlfunc.coalesce(sqlfunc.sum(TokenUsage.completion_tokens), 0),
            sqlfunc.coalesce(sqlfunc.sum(TokenUsage.total_tokens), 0),
            sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0.0),
            sqlfunc.max(TokenUsage.username),
            sqlfunc.max(TokenUsage.user_id),
            sqlfunc.max(TokenUsage.created_at),
        )
        .where(TokenUsage.tenant_id == tid, TokenUsage.chat_id.isnot(None))
        .group_by(TokenUsage.chat_id)
    )
    if start is not None:
        stmt = stmt.where(TokenUsage.created_at >= start)
    if end is not None:
        stmt = stmt.where(TokenUsage.created_at < end)
    rows = (await session.execute(stmt)).all()

    users = (await session.execute(
        select(User).where(User.tenant_id == tid)
    )).scalars().all()
    users_map = {u.chat_id: u for u in users}
    roles_map = {
        r.id: r.name for r in (await session.execute(
            select(Role).where(Role.tenant_id == tid)
        )).scalars().all()
    }
    active_alerts = set((await session.execute(
        select(UsageAlert.chat_id).where(
            UsageAlert.tenant_id == tid, UsageAlert.status == "active"
        )
    )).scalars().all())

    user_rows = []
    for chat_id, prompt, completion, total, cost, username, user_id, last_at in rows:
        u = users_map.get(chat_id)
        cost = float(cost or 0.0)
        user_rows.append({
            "chat_id": chat_id,
            "user_id": (u.user_id if u else user_id),
            "username": (u.username if u and u.username else username),
            "role_name": roles_map.get(u.role_id, "—") if u else "—",
            "prompt_tokens": int(prompt or 0),
            "completion_tokens": int(completion or 0),
            "total_tokens": int(total or 0),
            "cost_usd": round(cost, 4),
            "is_active": bool(u.is_active) if u else False,
            "is_paused": bool(u.is_paused) if u else False,
            "paused_reason": u.paused_reason if u else None,
            "has_alert": chat_id in active_alerts,
            "over_threshold": (conf.threshold_usd > 0 and cost >= conf.threshold_usd),
            "last_activity": last_at.isoformat() if last_at else None,
        })

    user_rows.sort(key=lambda r: r["cost_usd"], reverse=True)

    return {
        "tenant_id": tid,
        "currency": "USD",
        "threshold_usd": conf.threshold_usd,
        "period": conf.period,
        "auto_pause": conf.auto_pause,
        "notify_telegram": conf.notify_telegram,
        "notify_email": conf.notify_email,
        "admin_email": conf.admin_email,
        "totals": {
            "total_tokens": sum(r["total_tokens"] for r in user_rows),
            "prompt_tokens": sum(r["prompt_tokens"] for r in user_rows),
            "completion_tokens": sum(r["completion_tokens"] for r in user_rows),
            "total_cost_usd": round(sum(r["cost_usd"] for r in user_rows), 4),
            "users_count": len(user_rows),
            "over_threshold_count": sum(1 for r in user_rows if r["over_threshold"]),
            "paused_count": sum(1 for r in user_rows if r["is_paused"]),
        },
        "usuarios": user_rows,
    }


@router.get("/consumo/historial")
async def consumo_historial(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
    chat_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source: str = "",
    limit: int = 100,
    offset: int = 0,
):
    """Historial de consumo con filtros por fecha, cliente y usuario."""
    from mind.db.models import Tenant, TokenUsage

    tid = admin.get("tenant_id") if admin.get("role") == "tenant_admin" else tenant_id
    start = _parse_dt(date_from)
    end = _parse_dt(date_to, end=True)

    base = select(TokenUsage)
    count_stmt = select(sqlfunc.count()).select_from(TokenUsage)
    if tid:
        base = base.where(TokenUsage.tenant_id == tid)
        count_stmt = count_stmt.where(TokenUsage.tenant_id == tid)
    if chat_id is not None:
        base = base.where(TokenUsage.chat_id == chat_id)
        count_stmt = count_stmt.where(TokenUsage.chat_id == chat_id)
    if start is not None:
        base = base.where(TokenUsage.created_at >= start)
        count_stmt = count_stmt.where(TokenUsage.created_at >= start)
    if end is not None:
        base = base.where(TokenUsage.created_at < end)
        count_stmt = count_stmt.where(TokenUsage.created_at < end)
    if source:
        base = base.where(TokenUsage.source == source)
        count_stmt = count_stmt.where(TokenUsage.source == source)

    total = (await session.execute(count_stmt)).scalar() or 0
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    base = base.order_by(TokenUsage.created_at.desc()).limit(limit).offset(offset)
    logs = (await session.execute(base)).scalars().all()

    tenant_names = {
        t.id: t.name for t in (await session.execute(select(Tenant))).scalars().all()
    }

    return {
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "rows": [
            {
                "id": log.id,
                "tenant_id": log.tenant_id,
                "tenant_name": tenant_names.get(log.tenant_id, "—"),
                "chat_id": log.chat_id,
                "user_id": log.user_id,
                "username": log.username,
                "model": log.model,
                "prompt_tokens": log.prompt_tokens,
                "completion_tokens": log.completion_tokens,
                "total_tokens": log.total_tokens,
                "cost_usd": round(float(log.cost_usd or 0.0), 4),
                "source": log.source,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


@router.get("/consumo/alertas")
async def consumo_alertas(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
    status_filter: str = "",
):
    from mind.db.models import Tenant, UsageAlert

    tid = admin.get("tenant_id") if admin.get("role") == "tenant_admin" else tenant_id
    stmt = select(UsageAlert).order_by(UsageAlert.created_at.desc()).limit(300)
    if tid:
        stmt = stmt.where(UsageAlert.tenant_id == tid)
    if status_filter:
        stmt = stmt.where(UsageAlert.status == status_filter)
    alerts = (await session.execute(stmt)).scalars().all()

    tenant_names = {
        t.id: t.name for t in (await session.execute(select(Tenant))).scalars().all()
    }
    return [
        {
            "id": a.id,
            "tenant_id": a.tenant_id,
            "tenant_name": tenant_names.get(a.tenant_id, "—"),
            "chat_id": a.chat_id,
            "user_id": a.user_id,
            "username": a.username,
            "threshold_usd": a.threshold_usd,
            "total_cost_usd": round(float(a.total_cost_usd or 0.0), 4),
            "total_tokens": a.total_tokens,
            "period_key": a.period_key,
            "status": a.status,
            "notified": a.notified,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        }
        for a in alerts
    ]


@router.patch("/consumo/alertas/{alert_id}/reconocer")
async def consumo_alerta_reconocer(
    alert_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import UsageAlert
    alert = (await session.execute(
        select(UsageAlert).where(UsageAlert.id == alert_id)
    )).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    await session.commit()
    return {"ok": True}


@router.post("/consumo/usuarios/{chat_id}/pausar")
async def consumo_pausar_usuario(
    chat_id: int,
    body: UsagePauseRequest | None = None,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    """Pausa el acceso de un usuario por consumo excedido y le notifica."""
    from mind.db.models import Tenant, User
    from mind.usage.notifier import notify_user_paused

    tid = get_effective_tenant_id(admin, tenant_id)
    user = (await session.execute(
        select(User).where(User.chat_id == chat_id, User.tenant_id == tid)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    reason = (body.reason if body and body.reason else None) or "Pausado por consumo excedido"
    user.is_paused = True
    user.paused_reason = reason
    user.paused_at = datetime.now(timezone.utc)
    await session.commit()

    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tid)
    )).scalar_one_or_none()
    await notify_user_paused(tenant.bot_token if tenant else None, chat_id)
    return {"ok": True, "chat_id": chat_id, "is_paused": True}


@router.post("/consumo/usuarios/{chat_id}/reanudar")
async def consumo_reanudar_usuario(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    """Reactiva el acceso de un usuario pausado y le notifica."""
    from mind.db.models import Tenant, User
    from mind.usage.notifier import notify_user_resumed

    tid = get_effective_tenant_id(admin, tenant_id)
    user = (await session.execute(
        select(User).where(User.chat_id == chat_id, User.tenant_id == tid)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.is_paused = False
    user.paused_reason = None
    user.paused_at = None
    await session.commit()

    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tid)
    )).scalar_one_or_none()
    await notify_user_resumed(tenant.bot_token if tenant else None, chat_id)
    return {"ok": True, "chat_id": chat_id, "is_paused": False}


# ── PROMPTS PROGRAMADOS ───────────────────────────────────────────────────────

def _prompt_to_dict(p) -> dict:
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "name": p.name,
        "description": p.description or "",
        "prompt": p.prompt,
        "chat_id": p.chat_id,
        "chat_label": p.chat_label or "",
        "send_to_all": bool(getattr(p, "send_to_all", False)),
        "frequency": p.frequency,
        "cron_expression": p.cron_expression,
        "timezone": p.timezone,
        "is_active": p.is_active,
        "last_run_at": p.last_run_at.isoformat() if p.last_run_at else None,
        "last_status": p.last_status,
        "last_error": p.last_error,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _compose_and_validate_cron(
    frequency: str, hour: int, minute: int, weekday: int, custom: str | None
) -> str:
    from mind.scheduler.prompts import compose_cron
    from mind.scheduler.manager import validate_cron_expression

    try:
        cron = compose_cron(frequency, hour, minute, weekday, custom)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    valid = validate_cron_expression(cron)
    if not valid.get("valid"):
        raise HTTPException(status_code=422, detail=valid.get("message", "Cron inválido"))
    return cron


@router.get("/prompts/variables")
async def prompts_variables(admin=Depends(require_admin)):
    from mind.scheduler.prompts import available_variables
    return available_variables()


@router.get("/destinos")
async def destinos_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    """Usuarios y grupos conocidos por el bot, para elegir el destino de un prompt."""
    from mind.db.models import TelegramChat, User

    tid = get_effective_tenant_id(admin, tenant_id)
    items: dict[int, dict] = {}

    chats = (await session.execute(
        select(TelegramChat)
        .where(TelegramChat.tenant_id == tid)
        .order_by(TelegramChat.last_seen_at.desc())
    )).scalars().all()
    for c in chats:
        is_group = (c.chat_type or "private") in ("group", "supergroup", "channel")
        if is_group:
            label = c.title or f"Grupo {c.chat_id}"
            ctype = "group"
        else:
            label = (
                c.title
                or (f"@{c.username}" if c.username else None)
                or " ".join(p for p in [c.first_name, c.last_name] if p)
                or f"Usuario {c.chat_id}"
            )
            ctype = "user"
        items[c.chat_id] = {
            "chat_id": c.chat_id,
            "label": label,
            "type": ctype,
            "username": c.username,
        }

    users = (await session.execute(
        select(User).where(User.tenant_id == tid)
    )).scalars().all()
    for u in users:
        if u.chat_id in items:
            continue
        items[u.chat_id] = {
            "chat_id": u.chat_id,
            "label": (f"@{u.username}" if u.username else f"Usuario {u.user_id}"),
            "type": "user",
            "username": u.username,
        }

    return sorted(items.values(), key=lambda x: (x["type"], (x["label"] or "").lower()))


@router.get("/prompts")
async def prompts_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import ScheduledPrompt
    tid = get_effective_tenant_id(admin, tenant_id)
    rows = (await session.execute(
        select(ScheduledPrompt)
        .where(ScheduledPrompt.tenant_id == tid)
        .order_by(ScheduledPrompt.created_at.desc())
    )).scalars().all()

    from mind.scheduler.manager import get_scheduler
    next_map: dict[str, str] = {}
    try:
        sched = get_scheduler()
        for job in sched.get_jobs():
            if job.id.startswith("prompt:") and job.next_run_time:
                next_map[job.id] = job.next_run_time.isoformat()
    except Exception:
        pass

    result = []
    for p in rows:
        d = _prompt_to_dict(p)
        d["next_run_at"] = next_map.get(f"prompt:{p.id}")
        result.append(d)
    return result


@router.post("/prompts")
async def prompts_create(
    body: ScheduledPromptCreate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import ScheduledPrompt
    tid = get_effective_tenant_id(admin, tenant_id)
    cron = _compose_and_validate_cron(
        body.frequency, body.hour, body.minute, body.weekday, body.cron_expression
    )
    sp = ScheduledPrompt(
        tenant_id=tid,
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        prompt=body.prompt,
        chat_id=body.chat_id,
        chat_label=(body.chat_label or "").strip() or None,
        send_to_all=body.send_to_all,
        frequency=body.frequency,
        cron_expression=cron,
        timezone=body.timezone or "America/Bogota",
        is_active=body.is_active,
    )
    session.add(sp)
    await session.commit()
    await session.refresh(sp)

    try:
        from mind.scheduler.prompts import sync_prompt_job
        sync_prompt_job(sp)
    except Exception as exc:
        logger.warning("No se pudo programar el prompt %s: %s", sp.id, exc)

    return _prompt_to_dict(sp)


@router.put("/prompts/{prompt_id}")
async def prompts_update(
    prompt_id: int,
    body: ScheduledPromptUpdate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import ScheduledPrompt
    tid = get_effective_tenant_id(admin, tenant_id)
    sp = (await session.execute(
        select(ScheduledPrompt).where(
            ScheduledPrompt.id == prompt_id, ScheduledPrompt.tenant_id == tid
        )
    )).scalar_one_or_none()
    if not sp:
        raise HTTPException(status_code=404, detail="Prompt no encontrado")

    if body.name is not None:
        sp.name = body.name.strip()
    if body.description is not None:
        sp.description = body.description.strip() or None
    if body.prompt is not None:
        sp.prompt = body.prompt
    if body.chat_id is not None:
        sp.chat_id = body.chat_id
    if body.chat_label is not None:
        sp.chat_label = body.chat_label.strip() or None
    if body.send_to_all is not None:
        sp.send_to_all = body.send_to_all
    if body.timezone is not None:
        sp.timezone = body.timezone or "America/Bogota"
    if body.is_active is not None:
        sp.is_active = body.is_active

    # Recalcular cron si el formulario envió la programación
    scheduling_touched = any(v is not None for v in (
        body.frequency, body.hour, body.minute, body.weekday, body.cron_expression
    ))
    if scheduling_touched:
        freq = body.frequency or sp.frequency
        hour = body.hour if body.hour is not None else 8
        minute = body.minute if body.minute is not None else 0
        weekday = body.weekday if body.weekday is not None else 0
        custom = body.cron_expression
        if freq == "custom" and not custom:
            cron = sp.cron_expression
        else:
            cron = _compose_and_validate_cron(freq, hour, minute, weekday, custom)
        sp.cron_expression = cron
        sp.frequency = freq

    await session.commit()
    await session.refresh(sp)

    try:
        from mind.scheduler.prompts import sync_prompt_job
        sync_prompt_job(sp)
    except Exception as exc:
        logger.warning("No se pudo reprogramar el prompt %s: %s", sp.id, exc)

    return _prompt_to_dict(sp)


@router.patch("/prompts/{prompt_id}/toggle")
async def prompts_toggle(
    prompt_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import ScheduledPrompt
    tid = get_effective_tenant_id(admin, tenant_id)
    sp = (await session.execute(
        select(ScheduledPrompt).where(
            ScheduledPrompt.id == prompt_id, ScheduledPrompt.tenant_id == tid
        )
    )).scalar_one_or_none()
    if not sp:
        raise HTTPException(status_code=404, detail="Prompt no encontrado")
    sp.is_active = not sp.is_active
    await session.commit()
    try:
        from mind.scheduler.prompts import sync_prompt_job
        sync_prompt_job(sp)
    except Exception as exc:
        logger.warning("No se pudo cambiar estado del prompt %s: %s", sp.id, exc)
    return {"id": sp.id, "is_active": sp.is_active}


@router.delete("/prompts/{prompt_id}")
async def prompts_delete(
    prompt_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import ScheduledPrompt
    tid = get_effective_tenant_id(admin, tenant_id)
    await session.execute(
        delete(ScheduledPrompt).where(
            ScheduledPrompt.id == prompt_id, ScheduledPrompt.tenant_id == tid
        )
    )
    await session.commit()
    try:
        from mind.scheduler.prompts import remove_prompt_job
        remove_prompt_job(prompt_id)
    except Exception:
        pass
    return {"ok": True}


@router.post("/prompts/{prompt_id}/run")
async def prompts_run_now(
    prompt_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    """Ejecuta el prompt de inmediato y envía el resultado por Telegram."""
    from mind.scheduler.prompts import execute_prompt
    tid = get_effective_tenant_id(admin, tenant_id)
    return await execute_prompt(prompt_id, tid, send=True)


@router.post("/prompts/preview")
async def prompts_preview(
    body: PromptPreviewRequest,
    admin=Depends(require_admin),
    tenant_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Renderiza las variables {{...}} con los valores actuales del cliente."""
    from mind.db.models import Tenant
    from mind.scheduler.prompts import build_context, render_prompt
    tid = get_effective_tenant_id(admin, tenant_id)
    tenant = (await session.execute(select(Tenant).where(Tenant.id == tid))).scalar_one_or_none()
    return {"rendered": render_prompt(body.prompt, build_context(tenant))}


# ── BASE DE CONOCIMIENTO ──────────────────────────────────────────────────────

def _knowledge_to_dict(e) -> dict:
    return {
        "id": e.id,
        "tenant_id": e.tenant_id,
        "title": e.title,
        "content": e.content,
        "source": e.source or "",
        "tags": e.tags or "",
        "is_active": e.is_active,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


@router.get("/conocimiento")
async def knowledge_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import KnowledgeEntry
    tid = get_effective_tenant_id(admin, tenant_id)
    rows = (await session.execute(
        select(KnowledgeEntry)
        .where(KnowledgeEntry.tenant_id == tid)
        .order_by(KnowledgeEntry.updated_at.desc())
    )).scalars().all()
    return [_knowledge_to_dict(e) for e in rows]


@router.post("/conocimiento")
async def knowledge_create(
    body: KnowledgeCreate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import KnowledgeEntry
    tid = get_effective_tenant_id(admin, tenant_id)
    entry = KnowledgeEntry(
        tenant_id=tid,
        title=body.title.strip(),
        content=body.content,
        source=(body.source or "manual").strip() or "manual",
        tags=(body.tags or "").strip() or None,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return _knowledge_to_dict(entry)


@router.put("/conocimiento/{entry_id}")
async def knowledge_update(
    entry_id: int,
    body: KnowledgeUpdate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import KnowledgeEntry
    tid = get_effective_tenant_id(admin, tenant_id)
    entry = (await session.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id, KnowledgeEntry.tenant_id == tid
        )
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")

    if body.title is not None:
        entry.title = body.title.strip()
    if body.content is not None:
        entry.content = body.content
    if body.source is not None:
        entry.source = body.source.strip() or "manual"
    if body.tags is not None:
        entry.tags = body.tags.strip() or None
    if body.is_active is not None:
        entry.is_active = body.is_active
    await session.commit()
    await session.refresh(entry)
    return _knowledge_to_dict(entry)


@router.patch("/conocimiento/{entry_id}/toggle")
async def knowledge_toggle(
    entry_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import KnowledgeEntry
    tid = get_effective_tenant_id(admin, tenant_id)
    entry = (await session.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id, KnowledgeEntry.tenant_id == tid
        )
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    entry.is_active = not entry.is_active
    await session.commit()
    return {"id": entry.id, "is_active": entry.is_active}


@router.delete("/conocimiento/{entry_id}")
async def knowledge_delete(
    entry_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.db.models import KnowledgeEntry
    tid = get_effective_tenant_id(admin, tenant_id)
    await session.execute(
        delete(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id, KnowledgeEntry.tenant_id == tid
        )
    )
    await session.commit()
    return {"ok": True}
