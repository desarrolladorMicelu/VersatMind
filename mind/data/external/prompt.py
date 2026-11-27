"""Construye la sección de esquemas para bases de datos adicionales."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.auth.data_policy import SourcePolicy
from mind.db.models import TenantDatabase


async def build_extra_databases_prompt(
    session: AsyncSession, tenant_id: int, policy: SourcePolicy
) -> str:
    rows = (await session.execute(
        select(TenantDatabase)
        .where(TenantDatabase.tenant_id == tenant_id, TenantDatabase.is_active.is_(True))
        .order_by(TenantDatabase.alias)
    )).scalars().all()
    sections: list[str] = []
    for row in rows:
        if not policy.allows_db(row.alias):
            continue
        cfg = row.config or {}
        label = row.label or row.alias
        desc = str(cfg.get("schema_description") or "").strip()
        if desc:
            body = desc
        elif policy.restricted:
            allowed = sorted(policy.allowed_db_tables(row.alias))
            if not allowed:
                continue
            body = "Tablas permitidas: " + ", ".join(allowed) + "."
        else:
            body = "No hay descripción de esquema cargada. Consulta information_schema si es necesario."
        sections.append(
            f"### Base de datos `{row.alias}` — {label}\n"
            f"{body}\n"
            f"Usa 'ejecutar_consulta' con base='{row.alias}' para consultarla."
        )
    if not sections:
        return ""
    return (
        "\n\n## Bases de datos externas adicionales\n\n"
        "Cada bloque tiene un alias. Usa el parámetro `base` de 'ejecutar_consulta' "
        "con el alias correspondiente; si no se indica, se usa 'principal'.\n\n"
        + "\n\n".join(sections)
    )
