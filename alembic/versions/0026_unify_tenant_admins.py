"""Migra TenantAdmin a PortalUser con membership admin

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-26 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL_PERMISSIONS = [
    "READ_SALES", "READ_KPI", "READ_FINANCE", "GENERATE_REPORT", "MANAGE_TASKS",
    "READ_EXTERNAL_DB", "READ_MAIL", "READ_CALENDAR", "READ_CUSTOMER_PII",
]


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("tenant_admins", sa.Column("portal_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tenant_admins_portal_user", "tenant_admins", "portal_users",
        ["portal_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("idx_tenant_admins_portal", "tenant_admins", ["portal_user_id"])

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE roles SET is_admin = true WHERE lower(name) = 'admin'"))

    admins = bind.execute(sa.text(
        "SELECT id, tenant_id, username, password_hash, is_active FROM tenant_admins"
    )).mappings().all()

    for admin in admins:
        role_id = bind.execute(sa.text(
            "SELECT id FROM roles WHERE tenant_id = :tid AND lower(name) = 'admin' LIMIT 1"
        ), {"tid": admin["tenant_id"]}).scalar()
        if role_id is None:
            role_id = bind.execute(sa.text(
                """
                INSERT INTO roles (tenant_id, name, description, is_admin)
                VALUES (:tid, 'admin', 'Administrador con acceso completo', true)
                RETURNING id
                """
            ), {"tid": admin["tenant_id"]}).scalar()
        else:
            bind.execute(sa.text(
                "UPDATE roles SET is_admin = true WHERE id = :rid"
            ), {"rid": role_id})

        for perm in ALL_PERMISSIONS:
            bind.execute(sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_name)
                VALUES (:rid, :perm)
                ON CONFLICT (role_id, permission_name) DO NOTHING
                """
            ), {"rid": role_id, "perm": perm})

        portal_id = bind.execute(sa.text(
            "SELECT id FROM portal_users WHERE username = :u LIMIT 1"
        ), {"u": admin["username"]}).scalar()
        if portal_id is None:
            portal_id = bind.execute(sa.text(
                """
                INSERT INTO portal_users
                    (username, password_hash, full_name, is_active, must_change_password)
                VALUES (:u, :ph, :name, :active, false)
                RETURNING id
                """
            ), {
                "u": admin["username"], "ph": admin["password_hash"],
                "name": admin["username"], "active": admin["is_active"],
            }).scalar()
        else:
            bind.execute(sa.text(
                """
                UPDATE portal_users
                SET password_hash = :ph, is_active = :active,
                    must_change_password = false, temp_password_enc = NULL
                WHERE id = :pid
                """
            ), {"ph": admin["password_hash"], "active": admin["is_active"], "pid": portal_id})

        bind.execute(sa.text(
            """
            INSERT INTO memberships (portal_user_id, tenant_id, role_id, is_active)
            VALUES (:pid, :tid, :rid, :active)
            ON CONFLICT (portal_user_id, tenant_id)
            DO UPDATE SET role_id = EXCLUDED.role_id, is_active = EXCLUDED.is_active
            """
        ), {
            "pid": portal_id, "tid": admin["tenant_id"],
            "rid": role_id, "active": admin["is_active"],
        })

        bind.execute(sa.text(
            "UPDATE tenant_admins SET portal_user_id = :pid WHERE id = :aid"
        ), {"pid": portal_id, "aid": admin["id"]})


def downgrade() -> None:
    op.drop_index("idx_tenant_admins_portal", table_name="tenant_admins")
    op.drop_constraint("fk_tenant_admins_portal_user", "tenant_admins", type_="foreignkey")
    op.drop_column("tenant_admins", "portal_user_id")
    op.drop_column("roles", "is_admin")
