"""Fuentes JSON R2

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-26 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_SOURCES = [
    ("json:precios", "JSON · Precios Éxito"),
    ("json:historial", "JSON · Historial de cambios"),
]
JSON_ROLES = ["admin", "Gerencia", "Comercial", "Contabilidad"]


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("json_sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    bind = op.get_bind()
    tenants = bind.execute(sa.text("SELECT id FROM tenants")).scalars().all()
    for tenant_id in tenants:
        for key, display in JSON_SOURCES:
            bind.execute(sa.text(
                """
                INSERT INTO data_sources (tenant_id, kind, source_key, display_name, is_active)
                VALUES (:tid, 'json_r2', :key, :display, true)
                ON CONFLICT (tenant_id, kind, source_key) DO NOTHING
                """
            ), {"tid": tenant_id, "key": key, "display": display})

        for role_name in JSON_ROLES:
            role_id = bind.execute(sa.text(
                "SELECT id FROM roles WHERE tenant_id = :tid AND lower(name) = lower(:name) LIMIT 1"
            ), {"tid": tenant_id, "name": role_name}).scalar()
            if role_id is None:
                continue
            bind.execute(sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_name)
                VALUES (:rid, 'READ_JSON_DATA')
                ON CONFLICT (role_id, permission_name) DO NOTHING
                """
            ), {"rid": role_id})
            for key, _display in JSON_SOURCES:
                bind.execute(sa.text(
                    """
                    INSERT INTO role_source_permissions (role_id, source_id, access)
                    SELECT :rid, id, 'read' FROM data_sources
                    WHERE tenant_id = :tid AND source_key = :key
                    ON CONFLICT (role_id, source_id) DO NOTHING
                    """
                ), {"rid": role_id, "tid": tenant_id, "key": key})


def downgrade() -> None:
    op.drop_column("tenants", "json_sources")
