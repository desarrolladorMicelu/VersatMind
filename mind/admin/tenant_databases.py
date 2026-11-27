"""CRUD de bases de datos externas adicionales por tenant."""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import require_superadmin
from mind.db.base import get_session
from mind.db.models import DataSource, Role, RoleSourcePermission, Tenant, TenantDatabase

router = APIRouter(prefix="/api/admin/tenants", tags=["tenant-databases"])

ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


class DatabasePayload(BaseModel):
    alias: str
    label: str = ""
    engine: str = "postgresql"
    host: str = ""
    port: int = 5432
    database: str = ""
    user: str = ""
    password: str = ""
    schema_name: str = "public"
    tables: list[str] = []
    schema_description: str | None = None
    is_active: bool = True


def _config_from_body(body: DatabasePayload, existing: dict | None = None) -> dict:
    stored = existing or {}
    password = body.password or stored.get("password") or ""
    return {
        "engine": "postgresql",
        "host": body.host.strip(),
        "port": int(body.port or 5432),
        "database": body.database.strip(),
        "user": body.user.strip(),
        "password": password,
        "schema": (body.schema_name or "public").strip() or "public",
        "tables": [t.strip() for t in body.tables if t.strip()],
        "schema_description": body.schema_description or stored.get("schema_description"),
    }


def _secretless(row: TenantDatabase) -> dict:
    cfg = dict(row.config or {})
    cfg.pop("password", None)
    return {
        "id": row.id,
        "alias": row.alias,
        "label": row.label,
        "engine": row.engine,
        "is_active": row.is_active,
        "host": cfg.get("host", ""),
        "port": cfg.get("port", 5432),
        "database": cfg.get("database", ""),
        "user": cfg.get("user", ""),
        "schema_name": cfg.get("schema", "public"),
        "tables": cfg.get("tables", []),
        "schema_description": cfg.get("schema_description"),
    }


async def _tenant(session: AsyncSession, tenant_id: int) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return tenant


async def _sync_sources(
    session: AsyncSession, tenant_id: int, alias: str, label: str,
    tables: list[str], is_active: bool,
) -> None:
    await session.execute(delete(DataSource).where(
        DataSource.tenant_id == tenant_id,
        or_(
            DataSource.source_key == f"db:{alias}",
            DataSource.source_key.like(f"db:{alias}:%"),
        ),
    ))
    display = label.strip() or alias
    session.add(DataSource(
        tenant_id=tenant_id, kind="external_db",
        source_key=f"db:{alias}", display_name=f"Base de datos · {display}",
        is_active=is_active,
    ))
    for table in dict.fromkeys(tables):
        session.add(DataSource(
            tenant_id=tenant_id, kind="external_db_table",
            source_key=f"db:{alias}:{table}",
            display_name=f"{display} · {table}", is_active=is_active,
        ))
    await session.flush()


    sources = (await session.execute(
        select(DataSource).where(
            DataSource.tenant_id == tenant_id,
            or_(
                DataSource.source_key == f"db:{alias}",
                DataSource.source_key.like(f"db:{alias}:%"),
            ),
        )
    )).scalars().all()
    admin_roles = (await session.execute(
        select(Role).where(
            Role.tenant_id == tenant_id,
            Role.name.in_(["admin", "Gerencia"]),
        )
    )).scalars().all()
    for role in admin_roles:
        has_policy = (await session.execute(
            select(RoleSourcePermission.role_id).where(
                RoleSourcePermission.role_id == role.id
            ).limit(1)
        )).first()
        if has_policy is None:
            continue
        for src in sources:
            session.add(RoleSourcePermission(
                role_id=role.id, source_id=src.id, access="read",
            ))
    await session.flush()


async def _validate_alias(session: AsyncSession, tenant_id: int, alias: str, exclude_id: int | None = None) -> None:
    alias = alias.strip().lower()
    if not ALIAS_RE.match(alias):
        raise HTTPException(status_code=422, detail="Alias inválido (usa minúsculas, 2-32 caracteres, letras, números, guion o guion bajo)")
    if alias in ("principal", "ofima"):
        raise HTTPException(status_code=409, detail="Ese alias está reservado")
    stmt = select(TenantDatabase.id).where(
        TenantDatabase.tenant_id == tenant_id,
        TenantDatabase.alias == alias,
    )
    if exclude_id is not None:
        stmt = stmt.where(TenantDatabase.id != exclude_id)
    if (await session.execute(stmt.limit(1))).first():
        raise HTTPException(status_code=409, detail="Ya existe una base con ese alias")


@router.get("/{tenant_id}/databases")
async def list_databases(
    tenant_id: int,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    await _tenant(session, tenant_id)
    rows = (await session.execute(
        select(TenantDatabase).where(TenantDatabase.tenant_id == tenant_id).order_by(TenantDatabase.created_at)
    )).scalars().all()
    return [_secretless(r) for r in rows]


@router.post("/{tenant_id}/databases")
async def create_database(
    tenant_id: int,
    body: DatabasePayload,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    await _tenant(session, tenant_id)
    alias = body.alias.strip().lower()
    await _validate_alias(session, tenant_id, alias)
    config = _config_from_body(body)
    row = TenantDatabase(
        tenant_id=tenant_id, alias=alias,
        label=body.label.strip() or alias,
        engine="postgresql", config=config, is_active=body.is_active,
    )
    session.add(row)
    await session.flush()
    await _sync_sources(session, tenant_id, alias, row.label, config.get("tables") or [], body.is_active)
    await session.commit()
    await session.refresh(row)
    return _secretless(row)


@router.put("/{tenant_id}/databases/{database_id}")
async def update_database(
    tenant_id: int,
    database_id: int,
    body: DatabasePayload,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(TenantDatabase, database_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Base de datos no encontrada")
    await _validate_alias(session, tenant_id, body.alias, exclude_id=database_id)
    alias = body.alias.strip().lower()
    old_alias = row.alias
    config = _config_from_body(body, row.config or {})
    row.alias = alias
    row.label = body.label.strip() or alias
    row.config = config
    row.is_active = body.is_active
    if old_alias != alias:
        await session.execute(delete(DataSource).where(
            DataSource.tenant_id == tenant_id,
            or_(
                DataSource.source_key == f"db:{old_alias}",
                DataSource.source_key.like(f"db:{old_alias}:%"),
            ),
        ))
    await _sync_sources(session, tenant_id, alias, row.label, config.get("tables") or [], body.is_active)
    await session.commit()
    await session.refresh(row)
    return _secretless(row)


@router.delete("/{tenant_id}/databases/{database_id}")
async def delete_database(
    tenant_id: int,
    database_id: int,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(TenantDatabase, database_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Base de datos no encontrada")
    await session.execute(delete(DataSource).where(
        DataSource.tenant_id == tenant_id,
        or_(
            DataSource.source_key == f"db:{row.alias}",
            DataSource.source_key.like(f"db:{row.alias}:%"),
        ),
    ))
    await session.delete(row)
    await session.commit()
    return {"ok": True}


@router.post("/{tenant_id}/databases/test")
async def test_database(
    tenant_id: int,
    body: DatabasePayload,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    await _tenant(session, tenant_id)
    from mind.data.external.postgresql import test_connection
    creds = _config_from_body(body)
    try:
        tables = await asyncio.wait_for(test_connection(creds), timeout=15) or []
        return {"ok": True, "tables": tables}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout conectando a la base externa (15 s)."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/{tenant_id}/databases/discover")
async def discover_database(
    tenant_id: int,
    body: DatabasePayload,
    admin=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    await _tenant(session, tenant_id)
    from mind.data.external.schema_discovery import introspect_schema, generate_schema_description
    creds = _config_from_body(body)
    try:
        async def _discover():
            raw = await introspect_schema(creds, tables=creds.get("tables") or [])
            if not raw:
                return ""
            return await generate_schema_description(raw)
        description = await asyncio.wait_for(_discover(), timeout=90)
        return {"schema_description": description}
    except asyncio.TimeoutError:
        return {"error": "Timeout del descubrimiento de esquema (90 s)."}
    except Exception as exc:
        return {"error": str(exc)}
