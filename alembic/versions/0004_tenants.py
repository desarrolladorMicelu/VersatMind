"""multi-tenant: add tenants table and tenant_id to all tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-16 00:00:00.000000

Esta migración:
1. Crea la tabla tenants
2. Migra datos existentes al tenant por defecto (leído desde env vars)
3. Agrega tenant_id a todas las tablas existentes
4. Ajusta constraints (PK, UNIQUE, FK, índices)
"""
from typing import Sequence, Union
import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SYSTEM_PROMPT = """Eres Mind, un asistente ejecutivo de inteligencia artificial para la empresa.
Tu función es consultar datos reales de la empresa usando las herramientas disponibles.

REGLAS CRÍTICAS — NUNCA las ignores:
- Cuando el usuario pida datos de ventas, finanzas, productos, indicadores o cuentas por pagar: SIEMPRE llama la herramienta correspondiente PRIMERO. NUNCA respondas que no tienes acceso sin intentarlo.
- NUNCA digas "hay un problema técnico" sin haber intentado llamar la herramienta.
- NUNCA inventes datos. Si la herramienta retorna error, muestra el mensaje de error exacto al usuario.
- Responde en español siempre.
- Después de llamar una herramienta, interpreta los resultados y preséntelos de forma clara y ejecutiva."""


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Crear tabla tenants                                               #
    # ------------------------------------------------------------------ #
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("bot_token", sa.Text(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("admin_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("sqlserver_host", sa.Text(), nullable=True),
        sa.Column("sqlserver_db", sa.Text(), nullable=True),
        sa.Column("sqlserver_user", sa.Text(), nullable=True),
        sa.Column("sqlserver_password", sa.Text(), nullable=True),
        sa.Column("sqlserver_driver", sa.Text(), nullable=False,
                  server_default="ODBC Driver 18 for SQL Server"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    # ------------------------------------------------------------------ #
    # 2. Insertar tenant por defecto desde variables de entorno            #
    # ------------------------------------------------------------------ #
    bot_token    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    webhook_url  = os.environ.get("TELEGRAM_WEBHOOK_URL", "https://example.com")
    admin_chat   = int(os.environ.get("ADMIN_CHAT_ID", "0"))
    ss_host      = os.environ.get("SQLSERVER_HOST", "")
    ss_db        = os.environ.get("SQLSERVER_DB", "")
    ss_user      = os.environ.get("SQLSERVER_USER", "")
    ss_password  = os.environ.get("SQLSERVER_PASSWORD", "")
    ss_driver    = os.environ.get("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO tenants "
            "(name, slug, is_active, bot_token, webhook_url, admin_chat_id, "
            " sqlserver_host, sqlserver_db, sqlserver_user, sqlserver_password, sqlserver_driver) "
            "VALUES (:name, :slug, true, :token, :webhook, :admin_chat, "
            "        :ss_host, :ss_db, :ss_user, :ss_pass, :ss_driver)"
        ).bindparams(
            name="Default Tenant",
            slug="default",
            token=bot_token,
            webhook=webhook_url,
            admin_chat=admin_chat,
            ss_host=ss_host,
            ss_db=ss_db,
            ss_user=ss_user,
            ss_pass=ss_password,
            ss_driver=ss_driver,
        )
    )
    # Obtener el id del tenant recién creado
    result = bind.execute(sa.text("SELECT id FROM tenants WHERE slug = 'default'"))
    default_tenant_id = result.scalar()

    # ------------------------------------------------------------------ #
    # 3. roles: drop unique(name) → add tenant_id                         #
    # ------------------------------------------------------------------ #
    op.drop_constraint("roles_name_key", "roles", type_="unique")
    op.add_column("roles", sa.Column("tenant_id", sa.Integer(), nullable=True))
    bind.execute(sa.text(f"UPDATE roles SET tenant_id = {default_tenant_id}"))
    op.alter_column("roles", "tenant_id", nullable=False)
    op.create_foreign_key(
        "fk_roles_tenant_id", "roles", "tenants", ["tenant_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_roles_tenant_id", "roles", ["tenant_id"])

    # ------------------------------------------------------------------ #
    # 4. users: drop PK(chat_id) → add tenant_id → new PK(chat_id, tenant_id)
    # ------------------------------------------------------------------ #
    op.add_column("users", sa.Column("tenant_id", sa.Integer(), nullable=True))
    bind.execute(sa.text(f"UPDATE users SET tenant_id = {default_tenant_id}"))
    op.alter_column("users", "tenant_id", nullable=False)
    op.drop_constraint("users_pkey", "users", type_="primary")
    op.create_primary_key("users_pkey", "users", ["chat_id", "tenant_id"])
    op.create_foreign_key(
        "fk_users_tenant_id", "users", "tenants", ["tenant_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_users_tenant_chat", "users", ["tenant_id", "chat_id"])

    # ------------------------------------------------------------------ #
    # 5. conversation_history: add tenant_id, update index                #
    # ------------------------------------------------------------------ #
    op.add_column("conversation_history", sa.Column("tenant_id", sa.Integer(), nullable=True))
    bind.execute(sa.text(f"UPDATE conversation_history SET tenant_id = {default_tenant_id}"))
    op.alter_column("conversation_history", "tenant_id", nullable=False)
    op.create_foreign_key(
        "fk_conv_history_tenant_id", "conversation_history", "tenants",
        ["tenant_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_index("idx_conv_history_chat_id", table_name="conversation_history")
    op.create_index(
        "idx_conv_history_tenant_chat", "conversation_history",
        ["tenant_id", "chat_id", "created_at"],
    )

    # ------------------------------------------------------------------ #
    # 6. scheduled_tasks: add tenant_id, update index                     #
    # ------------------------------------------------------------------ #
    op.add_column("scheduled_tasks", sa.Column("tenant_id", sa.Integer(), nullable=True))
    bind.execute(sa.text(f"UPDATE scheduled_tasks SET tenant_id = {default_tenant_id}"))
    op.alter_column("scheduled_tasks", "tenant_id", nullable=False)
    op.create_foreign_key(
        "fk_scheduled_tasks_tenant_id", "scheduled_tasks", "tenants",
        ["tenant_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_index("idx_scheduled_tasks_chat_id", table_name="scheduled_tasks")
    op.create_index(
        "idx_scheduled_tasks_tenant_chat", "scheduled_tasks",
        ["tenant_id", "chat_id"],
    )

    # ------------------------------------------------------------------ #
    # 7. audit_log: add tenant_id, update index                           #
    # ------------------------------------------------------------------ #
    op.add_column("audit_log", sa.Column("tenant_id", sa.Integer(), nullable=True))
    bind.execute(sa.text(f"UPDATE audit_log SET tenant_id = {default_tenant_id}"))
    op.create_foreign_key(
        "fk_audit_log_tenant_id", "audit_log", "tenants",
        ["tenant_id"], ["id"], ondelete="SET NULL",
    )
    op.drop_index("idx_audit_log_chat_id", table_name="audit_log")
    op.create_index(
        "idx_audit_log_tenant_chat", "audit_log",
        ["tenant_id", "chat_id", "timestamp_utc"],
    )

    # ------------------------------------------------------------------ #
    # 8. agent_config: add tenant_id, drop old PK row constraint          #
    # ------------------------------------------------------------------ #
    op.add_column("agent_config", sa.Column("tenant_id", sa.Integer(), nullable=True))
    bind.execute(sa.text(f"UPDATE agent_config SET tenant_id = {default_tenant_id}"))
    op.alter_column("agent_config", "tenant_id", nullable=False)
    op.create_foreign_key(
        "fk_agent_config_tenant_id", "agent_config", "tenants",
        ["tenant_id"], ["id"], ondelete="CASCADE",
    )
    op.create_unique_constraint("uq_agent_config_tenant", "agent_config", ["tenant_id"])
    op.create_index("idx_agent_config_tenant", "agent_config", ["tenant_id"])

    # ------------------------------------------------------------------ #
    # 9. access_requests: drop unique(chat_id) → add tenant_id            #
    # ------------------------------------------------------------------ #
    op.drop_constraint("access_requests_chat_id_key", "access_requests", type_="unique")
    op.add_column("access_requests", sa.Column("tenant_id", sa.Integer(), nullable=True))
    bind.execute(sa.text(f"UPDATE access_requests SET tenant_id = {default_tenant_id}"))
    op.alter_column("access_requests", "tenant_id", nullable=False)
    op.create_foreign_key(
        "fk_access_requests_tenant_id", "access_requests", "tenants",
        ["tenant_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_index("idx_access_requests_chat_id", table_name="access_requests")
    op.create_index(
        "idx_access_requests_tenant_chat", "access_requests",
        ["tenant_id", "chat_id"],
    )


def downgrade() -> None:
    # access_requests
    op.drop_index("idx_access_requests_tenant_chat", table_name="access_requests")
    op.drop_constraint("fk_access_requests_tenant_id", "access_requests", type_="foreignkey")
    op.drop_column("access_requests", "tenant_id")
    op.create_index("idx_access_requests_chat_id", "access_requests", ["chat_id"])
    op.create_unique_constraint("access_requests_chat_id_key", "access_requests", ["chat_id"])

    # agent_config
    op.drop_index("idx_agent_config_tenant", table_name="agent_config")
    op.drop_constraint("uq_agent_config_tenant", "agent_config", type_="unique")
    op.drop_constraint("fk_agent_config_tenant_id", "agent_config", type_="foreignkey")
    op.drop_column("agent_config", "tenant_id")

    # audit_log
    op.drop_constraint("fk_audit_log_tenant_id", "audit_log", type_="foreignkey")
    op.drop_column("audit_log", "tenant_id")
    op.drop_index("idx_audit_log_tenant_chat", table_name="audit_log")
    op.create_index("idx_audit_log_chat_id", "audit_log", ["chat_id", "timestamp_utc"])

    # scheduled_tasks
    op.drop_index("idx_scheduled_tasks_tenant_chat", table_name="scheduled_tasks")
    op.drop_constraint("fk_scheduled_tasks_tenant_id", "scheduled_tasks", type_="foreignkey")
    op.drop_column("scheduled_tasks", "tenant_id")
    op.create_index("idx_scheduled_tasks_chat_id", "scheduled_tasks", ["chat_id"])

    # conversation_history
    op.drop_index("idx_conv_history_tenant_chat", table_name="conversation_history")
    op.drop_constraint("fk_conv_history_tenant_id", "conversation_history", type_="foreignkey")
    op.drop_column("conversation_history", "tenant_id")
    op.create_index("idx_conv_history_chat_id", "conversation_history", ["chat_id", "created_at"])

    # users
    op.drop_index("idx_users_tenant_chat", table_name="users")
    op.drop_constraint("fk_users_tenant_id", "users", type_="foreignkey")
    op.drop_constraint("users_pkey", "users", type_="primary")
    op.create_primary_key("users_pkey", "users", ["chat_id"])
    op.drop_column("users", "tenant_id")

    # roles
    op.drop_index("idx_roles_tenant_id", table_name="roles")
    op.drop_constraint("fk_roles_tenant_id", "roles", type_="foreignkey")
    op.drop_column("roles", "tenant_id")
    op.create_unique_constraint("roles_name_key", "roles", ["name"])

    # tenants
    op.drop_table("tenants")
