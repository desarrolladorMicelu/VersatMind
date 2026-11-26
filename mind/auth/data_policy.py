"""
Política de acceso a fuentes de datos por rol.

Reglas:
- Si un rol/usuario no tiene filas en role_source_permissions, se mantiene el
  comportamiento legado: el permiso funcional es suficiente.
- Si tiene filas, la política es una allowlist: solo las fuentes con access
  'read' están permitidas. Una fila 'none' siempre gana.
- Para bases de datos, las tablas se validan contra claves:
  ofima:<tabla>, external_db:<tabla>, sheets:<pestaña>, excel:<hoja>.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.db.models import (
    DataSource,
    Membership,
    RolePermission,
    RoleSourcePermission,
    UserRole,
)

SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}

# Tablas de OFIMA que toca cada herramienta. Las claves se normalizan a
# minúsculas y se comparan contra las fuentes `ofima:<tabla>`.
TOOL_TABLES: dict[str, frozenset[str]] = {
    "consultar_ventas": frozenset({"mvtrade"}),
    "consultar_ventas_detalle": frozenset({"mvtrade"}),
    "consultar_indicadores": frozenset({"mvtrade", "vcxp"}),
    "consultar_finanzas": frozenset({"vcxp", "vabonos", "mvcuadre"}),
    "consultar_productos": frozenset({"mtmercia"}),
    "consultar_cxp": frozenset({"vcxp"}),
    "catalogo_precios": frozenset({"mtmercia", "mvprecio"}),
    "stock_celulares": frozenset({"mtmercia", "mtseries"}),
    "gangazos": frozenset({"mtmercia", "mtseries", "xmyct_tecnico_series"}),
    "ventas_recientes": frozenset({"ventas_bodega"}),
    "inventario_bodega": frozenset({"mtmercia", "mtseries"}),
    "validar_imei": frozenset({"mtmercia", "mtseries"}),
    "historial_cliente": frozenset({"clientes", "mvtrade", "v_clientes_fac"}),
    "buscar_cliente": frozenset({"clientes"}),
    "direccion_proveedor": frozenset({"mtprocli"}),
    "estado_sincronizacion_clientes": frozenset({"espclientes", "mtprocli"}),
    "inventario_activos": frozenset({"mtmercia", "mtseries"}),
    "cliente_completo": frozenset({"mtprocli"}),
    "factura_reciente_cliente": frozenset({"mvtrade"}),
    "medios_pago": frozenset({"mtmedpag"}),
    "movimientos_contables": frozenset({"mtprocli", "mvto"}),
}

REPORT_TABLES: dict[str, frozenset[str]] = {
    "ventas": frozenset({"mvtrade"}),
    "finanzas": frozenset({"vcxp", "vabonos", "mvcuadre"}),
    "indicadores": frozenset({"mvtrade", "vcxp"}),
}

REPORT_PERMISSIONS: dict[str, str] = {
    "ventas": "READ_SALES",
    "finanzas": "READ_FINANCE",
    "indicadores": "READ_KPI",
}

JSON_TOOL_SOURCES = {
    "consultar_precios_exito": "json:precios",
    "resumen_precios_exito": "json:precios",
    "consultar_historial_exito": "json:historial",
    "resumen_historial_exito": "json:historial",
}

MAIL_TOOLS = frozenset({
    "correos_recientes", "buscar_correos", "leer_correo", "guardar_borrador_respuesta",
})
CALENDAR_TOOLS = frozenset({"eventos_calendario", "proximos_eventos"})


@dataclass(frozen=True)
class SourcePolicy:
    restricted: bool = False
    allowed: frozenset[str] = frozenset()
    denied: frozenset[str] = frozenset()

    def allows(self, source_key: str) -> bool:
        if not self.restricted:
            return True
        if source_key in self.denied:
            return False
        if source_key in self.allowed:
            return True
        # Permitir un grupo completo: external_db habilita external_db:<tabla>,
        # ofima habilita ofima:<tabla>, sheets habilita sheets:<pestaña>.
        if ":" in source_key:
            group = source_key.split(":", 1)[0]
            return group in self.allowed and group not in self.denied
        return False

    def allows_all(self, source_keys: Iterable[str]) -> bool:
        return all(self.allows(k) for k in source_keys)

    def allowed_tables(self) -> frozenset[str]:
        return frozenset(
            k.split(":", 1)[1].lower()
            for k in self.allowed
            if k.startswith("external_db:")
        )

    def keys_with_prefix(self, prefix: str) -> frozenset[str]:
        marker = f"{prefix}:"
        return frozenset(k[len(marker):] for k in self.allowed if k.startswith(marker))


def empty_policy() -> SourcePolicy:
    """Política no restrictiva (comportamiento legado)."""
    return SourcePolicy()


async def load_user_role_ids(session: AsyncSession, user) -> frozenset[int]:
    """Roles del usuario: user_roles + columna legada users.role_id."""
    if user is None:
        return frozenset()
    if getattr(user, "portal_user_id", None) is not None:
        rows = (await session.execute(
            select(Membership.role_id).where(
                Membership.portal_user_id == user.portal_user_id,
                Membership.tenant_id == user.tenant_id,
                Membership.is_active.is_(True),
            )
        )).scalars().all()
        return frozenset(int(r) for r in rows)
    ids: set[int] = set()
    legacy = getattr(user, "role_id", None)
    if legacy:
        ids.add(int(legacy))
    rows = (await session.execute(
        select(UserRole.role_id).where(
            UserRole.tenant_id == user.tenant_id,
            UserRole.chat_id == user.chat_id,
        )
    )).scalars().all()
    ids.update(int(r) for r in rows)
    return frozenset(ids)


async def load_permissions_for_roles(
    session: AsyncSession, role_ids: Iterable[int]
) -> frozenset[str]:
    role_ids = list(dict.fromkeys(int(r) for r in role_ids))
    if not role_ids:
        return frozenset()
    rows = (await session.execute(
        select(RolePermission.permission_name).where(RolePermission.role_id.in_(role_ids))
    )).scalars().all()
    return frozenset(rows)


async def load_source_policy(
    session: AsyncSession, role_ids: Iterable[int], tenant_id: int
) -> SourcePolicy:
    role_ids = list(dict.fromkeys(int(r) for r in role_ids))
    if not role_ids:
        return empty_policy()
    has_rows = (await session.execute(
        select(RoleSourcePermission.role_id).where(
            RoleSourcePermission.role_id.in_(role_ids)
        ).limit(1)
    )).first()
    if has_rows is None:
        return empty_policy()
    rows = (await session.execute(
        select(RoleSourcePermission.access, DataSource.source_key)
        .join(DataSource, DataSource.id == RoleSourcePermission.source_id)
        .where(
            RoleSourcePermission.role_id.in_(role_ids),
            DataSource.tenant_id == tenant_id,
            DataSource.is_active.is_(True),
        )
    )).all()
    allowed: set[str] = set()
    denied: set[str] = set()
    for access, key in rows:
        # Las tablas de PostgreSQL se comparan sin distinguir mayúsculas.
        if key.startswith("external_db:"):
            key = "external_db:" + key.split(":", 1)[1].lower()
        if access == "none":
            denied.add(key)
        else:
            allowed.add(key)
    # deny gana aunque otro rol permita la fuente
    allowed -= denied
    return SourcePolicy(restricted=True, allowed=frozenset(allowed), denied=frozenset(denied))


def tool_tables(tool_name: str) -> frozenset[str]:
    return TOOL_TABLES.get(tool_name, frozenset())


def tool_source_allowed(
    tool_name: str,
    permissions: frozenset[str],
    policy: SourcePolicy,
    params: dict | None = None,
) -> bool:
    """True si la fuente de la tool está permitida para la política dada."""
    if not policy.restricted:
        return True

    params = params or {}
    if tool_name == "generar_informe":
        tipo = str(params.get("tipo") or "").strip().lower()
        tables = REPORT_TABLES.get(tipo, frozenset())
        if tipo == "indicadores" and "READ_FINANCE" not in permissions:
            tables = tables - {"vcxp"}
        return policy.allows_all(f"ofima:{t}" for t in tables)

    if tool_name == "generar_informe_contable":
        return True

    if tool_name in JSON_TOOL_SOURCES:
        return policy.allows(JSON_TOOL_SOURCES[tool_name])
    if tool_name in MAIL_TOOLS:
        return policy.allows("mail")
    if tool_name in CALENDAR_TOOLS:
        return policy.allows("calendar")

    if tool_name == "consultar_sheet":
        hoja = str(params.get("hoja") or "").strip()
        if policy.allows("sheets"):
            return True
        if hoja:
            return policy.allows(f"sheets:{hoja}")
        return bool(policy.keys_with_prefix("sheets"))
    if tool_name == "consultar_excel":
        hoja = str(params.get("hoja") or "").strip()
        if policy.allows("excel"):
            return True
        if hoja:
            return policy.allows(f"excel:{hoja}")
        return bool(policy.keys_with_prefix("excel"))
    if tool_name == "consultar_alegra":
        return policy.allows("alegra")

    if tool_name == "ejecutar_consulta":
        # La validación real se hace con las tablas extraídas del SQL.
        return policy.allows("external_db") or bool(policy.allowed_tables())

    tables = tool_tables(tool_name)
    if not tables:
        return True

    # Indicadores: si no hay permiso de finanzas, no se exige vcxp.
    if tool_name == "consultar_indicadores" and "READ_FINANCE" not in permissions:
        tables = tables - {"vcxp"}
    return policy.allows_all(f"ofima:{t}" for t in tables)


def extract_sql_tables(sql: str) -> tuple[set[str], set[str]]:
    """
    Extrae tablas y esquemas referenciados por un SELECT PostgreSQL.
    Usa sqlglot; lanza ValueError si no se puede analizar.
    """
    try:
        import sqlglot
        from sqlglot import exp
    except Exception as exc:  # pragma: no cover - dependencia faltante
        raise ValueError("No se pudo validar la consulta SQL.") from exc

    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception as exc:
        raise ValueError("No se pudo analizar la consulta SQL.") from exc

    cte_names = {
        (cte.alias_or_name or "").strip().lower()
        for cte in tree.find_all(exp.CTE)
        if cte.alias_or_name
    }
    tables: set[str] = set()
    schemas: set[str] = set()
    for table in tree.find_all(exp.Table):
        name = (table.name or "").strip().lower()
        if name:
            tables.add(name)
        db = (table.db or "").strip().lower()
        if db:
            schemas.add(db)
    tables -= cte_names
    return tables, schemas


def validate_tool_call(
    tool_name: str,
    params: dict,
    permissions: frozenset[str],
    policy: SourcePolicy,
) -> None:
    """
    Valida requisitos dinámicos antes de ejecutar una herramienta.
    Lanza PermissionDeniedError con un mensaje apto para el usuario.
    """
    from mind.agent.tools.registry import PermissionDeniedError

    if tool_name == "generar_informe":
        tipo = str(params.get("tipo") or "").strip().lower()
        required = REPORT_PERMISSIONS.get(tipo)
        if required is None:
            raise PermissionDeniedError("Tipo de informe no permitido.")
        if required not in permissions:
            raise PermissionDeniedError("No tienes acceso a este tipo de informe.")
        tables = REPORT_TABLES.get(tipo, frozenset())
        if tipo == "indicadores" and "READ_FINANCE" not in permissions:
            tables = tables - {"vcxp"}
        if policy.restricted and not policy.allows_all(f"ofima:{t}" for t in tables):
            raise PermissionDeniedError("No tienes acceso a los datos de este informe.")

    if tool_name == "consultar_indicadores" and "READ_KPI" not in permissions:
        raise PermissionDeniedError("No tienes acceso a los indicadores.")

    if tool_name == "ejecutar_consulta":
        sql = str(params.get("sql") or "")
        try:
            tables, schemas = extract_sql_tables(sql)
        except ValueError:
            if policy.restricted:
                raise PermissionDeniedError("No se pudo validar el acceso a la consulta.")
            tables, schemas = set(), set()

        if any(s in SYSTEM_SCHEMAS for s in schemas):
            raise PermissionDeniedError("No tienes acceso a esa información.")

        if policy.restricted:
            allowed = policy.allowed_tables()
            if not policy.allows("external_db"):
                if not tables or not set(tables).issubset(allowed):
                    raise PermissionDeniedError("No tienes acceso a una o más tablas de la consulta.")

    if tool_name in JSON_TOOL_SOURCES and policy.restricted and not policy.allows(JSON_TOOL_SOURCES[tool_name]):
        raise PermissionDeniedError("No tienes acceso a esa fuente JSON.")
    if tool_name in MAIL_TOOLS and policy.restricted and not policy.allows("mail"):
        raise PermissionDeniedError("No tienes acceso al correo.")
    if tool_name in CALENDAR_TOOLS and policy.restricted and not policy.allows("calendar"):
        raise PermissionDeniedError("No tienes acceso al calendario.")
    if tool_name == "consultar_sheet" and policy.restricted:
        hoja = str(params.get("hoja") or "").strip()
        if not (policy.allows("sheets") or (hoja and policy.allows(f"sheets:{hoja}"))):
            raise PermissionDeniedError("No tienes acceso a esa hoja de cálculo.")
    if tool_name == "consultar_excel" and policy.restricted:
        hoja = str(params.get("hoja") or "").strip()
        if not (policy.allows("excel") or (hoja and policy.allows(f"excel:{hoja}"))):
            raise PermissionDeniedError("No tienes acceso a esa hoja de Excel.")
    if tool_name == "consultar_alegra" and policy.restricted and not policy.allows("alegra"):
        raise PermissionDeniedError("No tienes acceso a Alegra.")

    tables = tool_tables(tool_name)
    if tables:
        if tool_name == "consultar_indicadores" and "READ_FINANCE" not in permissions:
            tables = tables - {"vcxp"}
        if policy.restricted and not policy.allows_all(f"ofima:{t}" for t in tables):
            raise PermissionDeniedError("No tienes acceso a la información solicitada.")


def source_key_for_tool(tool_name: str) -> str | None:
    """Clave principal para auditoría/logs."""
    if tool_name in JSON_TOOL_SOURCES:
        return JSON_TOOL_SOURCES[tool_name]
    if tool_name in MAIL_TOOLS:
        return "mail"
    if tool_name in CALENDAR_TOOLS:
        return "calendar"
    if tool_name == "consultar_sheet":
        return "sheets"
    if tool_name == "consultar_excel":
        return "excel"
    if tool_name == "consultar_alegra":
        return "alegra"
    if tool_name == "ejecutar_consulta":
        return "external_db"
    tables = tool_tables(tool_name)
    return f"ofima:{next(iter(tables))}" if tables else None
