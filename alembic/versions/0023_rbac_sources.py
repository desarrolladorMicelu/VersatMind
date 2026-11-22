"""RBAC por fuente/tabla y roles múltiples

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-22 00:00:00.000000

Crea data_sources, role_source_permissions y user_roles. Backfillea
user_roles desde users.role_id y siembra fuentes + roles por defecto
(Gerencia, Comercial, Contabilidad, Logística, admin) para cada tenant.

No elimina ni modifica roles existentes. Los roles existentes quedan sin
filas en role_source_permissions, por lo que conservan el comportamiento
legado (acceso permitido según su permiso funcional).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OFIMA_TABLES = [
    "clientes", "espclientes", "mtmedpag", "mtprocli", "mtseries", "mvto",
    "mtmercia", "mvcuadre", "mvprecio", "mvtrade", "vabonos", "vcxp",
    "vseriesutilidad", "v_clientes_fac", "xmyct_tecnico_series", "ventas_bodega",
]

ALL_PERMISSIONS = [
    "READ_SALES", "READ_KPI", "READ_FINANCE", "GENERATE_REPORT", "MANAGE_TASKS",
    "READ_EXTERNAL_DB", "READ_MAIL", "READ_CALENDAR", "READ_CUSTOMER_PII",
]

DEFAULT_ROLES = {
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
        "permissions": ["READ_SALES", "READ_KPI", "GENERATE_REPORT"],
        "sources": [
            "ofima:clientes", "ofima:espclientes", "ofima:mtmercia",
            "ofima:mtseries", "ofima:mvprecio", "ofima:mvtrade",
            "ofima:v_clientes_fac", "ofima:ventas_bodega",
            "ofima:xmyct_tecnico_series", "knowledge",
        ],
    },
    "Contabilidad": {
        "description": "Finanzas, contabilidad, cartera y reportes",
        "permissions": [
            "READ_SALES", "READ_KPI", "READ_FINANCE", "GENERATE_REPORT",
            "READ_EXTERNAL_DB", "READ_CUSTOMER_PII",
        ],
        "sources": [
            "ofima:clientes", "ofima:espclientes", "ofima:mtmedpag", "ofima:mtprocli",
            "ofima:mvtrade", "ofima:mvto", "ofima:mvcuadre",
            "ofima:vabonos", "ofima:vcxp", "ofima:v_clientes_fac",
            "alegra", "knowledge",
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


def _source_rows(tenant) -> list[tuple[str, str, str, bool]]:
    """(kind, source_key, display_name, is_active) para un tenant."""
    rows: list[tuple[str, str, str, bool]] = []

    if tenant["sqlserver_host"]:
        for table in OFIMA_TABLES:
            rows.append(("ofima_table", f"ofima:{table}", f"OFIMA · {table}", True))

    ext_db = tenant["external_db"] or {}
    if ext_db:
        rows.append(("external_db", "external_db", "Base de datos externa", True))
        for table in ext_db.get("tables") or []:
            key = str(table).strip().lower()
            if key:
                rows.append((
                    "external_db_table",
                    f"external_db:{key}",
                    f"Base de datos · {key}",
                    True,
                ))

    if tenant["external_sheets"]:
        rows.append(("sheets", "sheets", "Google Sheets", True))
    if tenant["external_excel"]:
        rows.append(("excel", "excel", "Excel / OneDrive", True))
    if tenant["external_alegra"]:
        rows.append(("alegra", "alegra", "Alegra", True))

    rows.extend([
        ("mail", "mail", "Correo", True),
        ("calendar", "calendar", "Calendario", True),
        ("knowledge", "knowledge", "Base de conocimiento", True),
    ])
    return rows


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "kind", "source_key", name="uq_data_source_tenant_kind_key"
        ),
    )
    op.create_index("idx_data_sources_tenant", "data_sources", ["tenant_id", "is_active"])

    op.create_table(
        "role_source_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("access", sa.Text(), nullable=False, server_default="read"),
        sa.CheckConstraint("access IN ('read', 'none')", name="ck_role_source_access"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "source_id"),
    )

    op.create_table(
        "user_roles",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chat_id"],
            ["users.tenant_id", "users.chat_id"],
            ondelete="CASCADE",
            name="fk_user_roles_user",
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "chat_id", "role_id"),
    )
    op.create_index("idx_user_roles_tenant_chat", "user_roles", ["tenant_id", "chat_id"])

    bind = op.get_bind()

    # Backfill: un rol por usuario desde el modelo legado.
    bind.execute(sa.text(
        """
        INSERT INTO user_roles (tenant_id, chat_id, role_id)
        SELECT tenant_id, chat_id, role_id FROM users
        ON CONFLICT (tenant_id, chat_id, role_id) DO NOTHING
        """
    ))

    tenants = bind.execute(sa.text(
        "SELECT id, sqlserver_host, external_db, external_sheets, external_excel, external_alegra FROM tenants"
    )).mappings().all()

    for tenant in tenants:
        tid = tenant["id"]

        for kind, key, display, active in _source_rows(tenant):
            bind.execute(sa.text(
                """
                INSERT INTO data_sources (tenant_id, kind, source_key, display_name, is_active)
                VALUES (:tid, :kind, :key, :display, :active)
                ON CONFLICT (tenant_id, kind, source_key) DO NOTHING
                """
            ), {"tid": tid, "kind": kind, "key": key, "display": display, "active": active})

        # Preserva el comportamiento de roles existentes: quien ya podía
        # ver ventas puede seguir viendo datos personales hasta que un admin
        # lo restrinja explícitamente.
        bind.execute(sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_name)
            SELECT rp.role_id, 'READ_CUSTOMER_PII'
            FROM role_permissions rp
            JOIN roles r ON r.id = rp.role_id
            WHERE r.tenant_id = :tid AND rp.permission_name = 'READ_SALES'
            ON CONFLICT (role_id, permission_name) DO NOTHING
            """
        ), {"tid": tid})

        for role_name, cfg in DEFAULT_ROLES.items():
            role_id = bind.execute(sa.text(
                "SELECT id FROM roles WHERE tenant_id = :tid AND name = :name LIMIT 1"
            ), {"tid": tid, "name": role_name}).scalar()

            if role_id is None:
                role_id = bind.execute(sa.text(
                    """
                    INSERT INTO roles (tenant_id, name, description)
                    VALUES (:tid, :name, :description) RETURNING id
                    """
                ), {"tid": tid, "name": role_name, "description": cfg["description"]}).scalar()

            for perm in cfg["permissions"]:
                bind.execute(sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_name)
                    VALUES (:rid, :perm)
                    ON CONFLICT (role_id, permission_name) DO NOTHING
                    """
                ), {"rid": role_id, "perm": perm})

            if cfg["sources"] == "all":
                bind.execute(sa.text(
                    """
                    INSERT INTO role_source_permissions (role_id, source_id, access)
                    SELECT :rid, id, 'read' FROM data_sources WHERE tenant_id = :tid
                    ON CONFLICT (role_id, source_id) DO NOTHING
                    """
                ), {"rid": role_id, "tid": tid})
            else:
                for key in cfg["sources"]:
                    bind.execute(sa.text(
                        """
                        INSERT INTO role_source_permissions (role_id, source_id, access)
                        SELECT :rid, id, 'read'
                        FROM data_sources
                        WHERE tenant_id = :tid AND source_key = :key
                        ON CONFLICT (role_id, source_id) DO NOTHING
                        """
                    ), {"rid": role_id, "tid": tid, "key": key})


def downgrade() -> None:
    op.drop_index("idx_user_roles_tenant_chat", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("role_source_permissions")
    op.drop_index("idx_data_sources_tenant", table_name="data_sources")
    op.drop_table("data_sources")
