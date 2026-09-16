"""
API REST del panel de administración — /api/admin/*
Todos los endpoints retornan JSON. El frontend React consume esta API.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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


# ── DASHBOARD ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import User, AuditLog, AccessRequest, ScheduledTask

    total_users = (await session.execute(
        select(sqlfunc.count()).select_from(User)
    )).scalar()
    pending_requests = (await session.execute(
        select(sqlfunc.count()).select_from(AccessRequest)
        .where(AccessRequest.status == "pending")
    )).scalar()
    total_interactions = (await session.execute(
        select(sqlfunc.count()).select_from(AuditLog)
        .where(AuditLog.event_type == "interaction")
    )).scalar()
    active_tasks = (await session.execute(
        select(sqlfunc.count()).select_from(ScheduledTask)
        .where(ScheduledTask.status == "active")
    )).scalar()
    errors_today = (await session.execute(
        select(sqlfunc.count()).select_from(AuditLog)
        .where(AuditLog.status == "error")
    )).scalar()

    recent_logs = (await session.execute(
        select(AuditLog).order_by(AuditLog.timestamp_utc.desc()).limit(10)
    )).scalars().all()

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
):
    from mind.db.models import AgentConfig
    cfg = (await session.execute(select(AgentConfig).limit(1))).scalar_one_or_none()
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
):
    from mind.db.models import AgentConfig
    cfg = (await session.execute(select(AgentConfig).limit(1))).scalar_one_or_none()
    if cfg:
        cfg.system_prompt = body.system_prompt
        cfg.model = body.model
        cfg.temperature = max(0.0, min(2.0, body.temperature))
        cfg.conversation_window = max(1, min(100, body.conversation_window))
        cfg.max_tool_cycles = max(1, min(20, body.max_tool_cycles))
    else:
        session.add(AgentConfig(**body.model_dump()))
    await session.commit()
    logger.info("AgentConfig actualizado por %s", admin.get("sub"))
    return {"ok": True}


# ── USUARIOS ─────────────────────────────────────────────────────────────────

@router.get("/usuarios")
async def usuarios_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import User, Role
    users = (await session.execute(
        select(User).order_by(User.created_at.desc())
    )).scalars().all()
    roles_map = {
        r.id: r.name
        for r in (await session.execute(select(Role))).scalars().all()
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
):
    from mind.db.models import User
    user = (await session.execute(
        select(User).where(User.chat_id == chat_id)
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
):
    from mind.db.models import User
    user = (await session.execute(
        select(User).where(User.chat_id == chat_id)
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
):
    from mind.db.models import User
    await session.execute(delete(User).where(User.chat_id == chat_id))
    await session.commit()
    return {"ok": True}


# ── ACCESOS ──────────────────────────────────────────────────────────────────

@router.get("/accesos")
async def accesos_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import AccessRequest
    reqs = (await session.execute(
        select(AccessRequest).order_by(AccessRequest.created_at.desc())
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
):
    from mind.auth.access_requests import approve_user
    user = await approve_user(chat_id, session)
    await session.commit()
    if not user:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada o ya procesada")
    return {"ok": True}


@router.post("/accesos/{chat_id}/rechazar")
async def acceso_rechazar(
    chat_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.auth.access_requests import reject_request
    ok = await reject_request(chat_id, session)
    await session.commit()
    return {"ok": ok}


# ── ROLES ────────────────────────────────────────────────────────────────────

@router.get("/roles")
async def roles_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from mind.db.models import Role, RolePermission
    roles = (await session.execute(select(Role))).scalars().all()
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
    role = Role(name=body.name, description=body.description)
    session.add(role)
    await session.commit()
    return {"id": role.id, "name": role.name}


# ── HISTORIAL ────────────────────────────────────────────────────────────────

@router.get("/historial")
async def historial_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    chat_id: int | None = None,
):
    from mind.db.models import ConversationMessage, User
    users = (await session.execute(
        select(User).where(User.is_active == True)
    )).scalars().all()

    messages = []
    if chat_id:
        msgs = (await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.chat_id == chat_id)
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
):
    from mind.db.models import ConversationMessage
    await session.execute(
        delete(ConversationMessage).where(ConversationMessage.chat_id == chat_id)
    )
    await session.commit()
    return {"ok": True}


# ── AUDITORÍA ────────────────────────────────────────────────────────────────

@router.get("/auditoria")
async def auditoria_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    event_type: str = "",
    status_filter: str = "",
    limit: int = 100,
):
    from mind.db.models import AuditLog
    stmt = select(AuditLog).order_by(AuditLog.timestamp_utc.desc())
    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)
    if status_filter:
        stmt = stmt.where(AuditLog.status == status_filter)
    stmt = stmt.limit(min(limit, 500))
    logs = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": log.id,
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
):
    from mind.db.models import ScheduledTask
    tasks = (await session.execute(
        select(ScheduledTask).order_by(ScheduledTask.created_at.desc())
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
