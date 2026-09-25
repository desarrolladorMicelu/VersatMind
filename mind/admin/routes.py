"""
API REST del panel de administración — /api/admin/*
Multi-tenant: los endpoints de datos aceptan ?tenant_id= para filtrar.
- superadmin: puede ver todos los tenants, pasa tenant_id como query param
- tenant_admin: solo ve su tenant, el tenant_id viene del JWT
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import (
    create_access_token, require_admin, require_superadmin,
    verify_superadmin, get_effective_tenant_id,
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

class TenantAdminCreate(BaseModel):
    username: str
    password: str

class TenantAdminUpdate(BaseModel):
    password: str | None = None
    is_active: bool | None = None


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
    from passlib.context import CryptContext
    _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

    result = await session.execute(
        select(TenantAdmin).where(
            TenantAdmin.username == body.username,
            TenantAdmin.is_active.is_(True),
        )
    )
    ta = result.scalar_one_or_none()
    if ta is None or not _pwd.verify(body.password, ta.password_hash):
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
    from passlib.context import CryptContext
    _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
        password_hash=_pwd.hash(body.password),
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
    from passlib.context import CryptContext
    _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

    ta = (await session.execute(
        select(TenantAdmin).where(
            TenantAdmin.id == admin_id,
            TenantAdmin.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if not ta:
        raise HTTPException(status_code=404, detail="Admin no encontrado")

    if body.password:
        ta.password_hash = _pwd.hash(body.password)
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
    updates = body.model_dump(exclude_none=True)
    for key, val in updates.items():
        setattr(tenant, key, val)
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
