"""agent_config table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
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
    op.create_table(
        "agent_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False, server_default="openai/gpt-4o-mini"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("conversation_window", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("max_tool_cycles", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    # Insertar fila inicial con valores por defecto
    op.execute(
        sa.text(
            "INSERT INTO agent_config (system_prompt, model, temperature, conversation_window, max_tool_cycles) "
            "VALUES (:prompt, :model, :temp, :window, :cycles)"
        ).bindparams(
            prompt=DEFAULT_SYSTEM_PROMPT,
            model="openai/gpt-4o-mini",
            temp=0.7,
            window=20,
            cycles=5,
        )
    )


def downgrade() -> None:
    op.drop_table("agent_config")
