"""Roles y fuentes de datos por defecto para un tenant."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.db.models import DataSource, Role, RolePermission, RoleSourcePermission

OFIMA_TABLES = [
    "clientes", "espclientes", "mtmedpag", "mtprocli", "mtseries", "mvto",
    "mtmercia", "mvcuadre", "mvprecio", "mvtrade", "vabonos", "vcxp",
    "vseriesutilidad", "v_clientes_fac", "xmyct_tecnico_series", "ventas_bodega",
]

ALL_PERMISSIONS = [
    "READ_SALES", "READ_KPI", "READ_FINANCE", "GENERATE_REPORT", "MANAGE_TASKS",
    "READ_EXTERNAL_DB", "READ_MAIL", "READ_CALENDAR", "READ_CUSTOMER_PII",
    "READ_JSON_DATA",
]

DEFAULT_ROLES: dict[str, dict] = {
    "admin": {
        "description": "Administrador con acceso completo",
        "permissions": ALL_PERMISSIONS,
        "sources": "all",
    },
    "Gerencia": {
        "description": "Acceso completo de lectura para gerencia",
        "permissions": ALL_PERMISSIONS,
        "sources": "all",
    },
    "Comercial": {
        "description": "Ventas, clientes, inventario y KPIs (sin finanzas)",
        "permissions": ["READ_SALES", "READ_KPI", "GENERATE_REPORT", "READ_JSON_DATA"],
        "sources": [
            "ofima:clientes", "ofima:espclientes", "ofima:mtmercia",
            "ofima:mtseries", "ofima:mvprecio", "ofima:mvtrade",
            "ofima:v_clientes_fac", "ofima:ventas_bodega",
            "ofima:xmyct_tecnico_series", "json:precios", "json:historial", "knowledge",
        ],
    },
    "Contabilidad": {
        "description": "Finanzas, contabilidad, cartera y reportes",
        "permissions": [
            "READ_SALES", "READ_KPI", "READ_FINANCE", "GENERATE_REPORT",
            "READ_EXTERNAL_DB", "READ_CUSTOMER_PII", "READ_JSON_DATA",
        ],
        "sources": [
            "ofima:clientes", "ofima:espclientes", "ofima:mtmedpag", "ofima:mtprocli",
            "ofima:mvtrade", "ofima:mvto", "ofima:mvcuadre",
            "ofima:vabonos", "ofima:vcxp", "ofima:v_clientes_fac",
            "alegra", "json:precios", "json:historial", "knowledge",
        ],
    },
    "Logística": {
        "description": "Inventario, bodegas, productos y ventas",
        "permissions": ["READ_SALES", "READ_KPI", "GENERATE_REPORT"],
        "sources": [
            "ofima:espclientes", "ofima:mtmercia", "ofima:mtseries",
            "ofima:mvprecio", "ofima:ventas_bodega",
            "ofima:xmyct_tecnico_series", "knowledge",
        ],
    },
}


def source_rows_for_tenant(tenant) -> list[tuple[str, str, str, bool]]:
    rows: list[tuple[str, str, str, bool]] = []
    if getattr(tenant, "sqlserver_host", None):
        for table in OFIMA_TABLES:
            rows.append(("ofima_table", f"ofima:{table}", f"OFIMA · {table}", True))

    ext_db = getattr(tenant, "external_db", None) or {}
    if ext_db:
        rows.append(("external_db", "external_db", "Base de datos externa", True))
        for table in ext_db.get("tables") or []:
            key = str(table).strip().lower()
            if key:
                rows.append((
                    "external_db_table", f"external_db:{key}",
                    f"Base de datos · {key}", True,
                ))

    if getattr(tenant, "external_sheets", None):
        rows.append(("sheets", "sheets", "Google Sheets", True))
    if getattr(tenant, "external_excel", None):
        rows.append(("excel", "excel", "Excel / OneDrive", True))
    if getattr(tenant, "external_alegra", None):
        rows.append(("alegra", "alegra", "Alegra", True))

    rows.extend([
        ("json_r2", "json:precios", "JSON · Precios Éxito", True),
        ("json_r2", "json:historial", "JSON · Historial de cambios", True),
        ("mail", "mail", "Correo", True),
        ("calendar", "calendar", "Calendario", True),
        ("knowledge", "knowledge", "Base de conocimiento", True),
    ])
    return rows


async def seed_tenant_defaults(session: AsyncSession, tenant) -> None:
    """Crea fuentes y roles por defecto si faltan. No elimina nada existente."""
    tid = tenant.id

    existing_sources = {
        (s.kind, s.source_key): s
        for s in (await session.execute(
            select(DataSource).where(DataSource.tenant_id == tid)
        )).scalars().all()
    }
    for kind, key, display, active in source_rows_for_tenant(tenant):
        if (kind, key) in existing_sources:
            continue
        src = DataSource(
            tenant_id=tid, kind=kind, source_key=key,
            display_name=display, is_active=active,
        )
        session.add(src)
        existing_sources[(kind, key)] = src
    await session.flush()

    sources_by_key = {s.source_key: s for s in existing_sources.values() if s.id}
    # Releer para obtener IDs de las fuentes recién creadas.
    all_sources = (await session.execute(
        select(DataSource).where(DataSource.tenant_id == tid)
    )).scalars().all()
    sources_by_key = {s.source_key: s for s in all_sources}

    existing_roles = {
        r.name: r for r in (await session.execute(
            select(Role).where(Role.tenant_id == tid)
        )).scalars().all()
    }

    for name, cfg in DEFAULT_ROLES.items():
        role = existing_roles.get(name)
        if role is None:
            role = Role(name=name, description=cfg["description"], tenant_id=tid)
            session.add(role)
            await session.flush()
            existing_roles[name] = role

        existing_perms = {
            p.permission_name
            for p in (await session.execute(
                select(RolePermission).where(RolePermission.role_id == role.id)
            )).scalars().all()
        }
        for perm in cfg["permissions"]:
            if perm not in existing_perms:
                session.add(RolePermission(role_id=role.id, permission_name=perm))

        # No tocar políticas ya configuradas: solo sembrar si el rol no tiene.
        has_policy = (await session.execute(
            select(RoleSourcePermission.role_id).where(
                RoleSourcePermission.role_id == role.id
            ).limit(1)
        )).first()
        if has_policy is not None:
            continue

        if cfg["sources"] == "all":
            for src in all_sources:
                session.add(RoleSourcePermission(
                    role_id=role.id, source_id=src.id, access="read"
                ))
        else:
            for key in cfg["sources"]:
                src = sources_by_key.get(key)
                if src is not None:
                    session.add(RoleSourcePermission(
                        role_id=role.id, source_id=src.id, access="read"
                    ))
    await session.flush()
