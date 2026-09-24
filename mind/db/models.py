"""
Modelos ORM de Mind by Versat — SQLAlchemy 2.x.
Multi-tenant: casi todas las tablas tienen tenant_id → ForeignKey(tenants.id).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Text,
    Float,
    Integer,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mind.db.base import Base


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------

class Tenant(Base):
    """Cliente / empresa. Cada bot de Telegram pertenece a un tenant."""
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # ej: "micelu"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Credenciales Telegram
    bot_token: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    admin_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Credenciales SQL Server OFIMA (cifradas en texto — mejora futura: vault)
    sqlserver_host: Mapped[str | None] = mapped_column(Text, nullable=True)
    sqlserver_db: Mapped[str | None] = mapped_column(Text, nullable=True)
    sqlserver_user: Mapped[str | None] = mapped_column(Text, nullable=True)
    sqlserver_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    sqlserver_driver: Mapped[str] = mapped_column(
        Text, nullable=False, default="ODBC Driver 18 for SQL Server"
    )

    # Base de datos externa del cliente (JSONB): engine, host, port, database,
    # user, password y schema_description generado por IA
    external_db: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Google Sheets externa del cliente (JSONB): spreadsheet_url,
    # spreadsheet_id, credentials (service account JSON) y schema_description
    external_sheets: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    roles: Mapped[list[Role]] = relationship("Role", back_populates="tenant", cascade="all, delete-orphan")
    users: Mapped[list[User]] = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    agent_configs: Mapped[list[AgentConfig]] = relationship("AgentConfig", back_populates="tenant", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} slug={self.slug!r} active={self.is_active}>"


# ---------------------------------------------------------------------------
# Roles y permisos
# ---------------------------------------------------------------------------

class Role(Base):
    """Roles del sistema (board_member, admin, etc.) — scoped por tenant."""
    __tablename__ = "roles"
    __table_args__ = (
        Index("idx_roles_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="roles")
    users: Mapped[list[User]] = relationship("User", back_populates="role")
    permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} tenant_id={self.tenant_id} name={self.name!r}>"


class RolePermission(Base):
    """Permisos asociados a un rol."""
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_name: Mapped[str] = mapped_column(Text, primary_key=True)

    role: Mapped[Role] = relationship("Role", back_populates="permissions")

    def __repr__(self) -> str:
        return f"<RolePermission role_id={self.role_id} permission={self.permission_name!r}>"


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

class User(Base):
    """Usuarios autorizados — scoped por tenant."""
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_tenant_chat", "tenant_id", "chat_id"),
    )

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="users")
    role: Mapped[Role] = relationship("Role", back_populates="users")

    def __repr__(self) -> str:
        return f"<User chat_id={self.chat_id} tenant_id={self.tenant_id} role_id={self.role_id}>"


# ---------------------------------------------------------------------------
# Historial de conversación
# ---------------------------------------------------------------------------

class ConversationMessage(Base):
    """Historial de conversación — scoped por tenant."""
    __tablename__ = "conversation_history"
    __table_args__ = (
        Index("idx_conv_history_tenant_chat", "tenant_id", "chat_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<ConversationMessage id={self.id} tenant_id={self.tenant_id} chat_id={self.chat_id}>"


# ---------------------------------------------------------------------------
# Tareas programadas
# ---------------------------------------------------------------------------

class ScheduledTask(Base):
    """Tareas programadas — scoped por tenant."""
    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        Index("idx_scheduled_tasks_tenant_chat", "tenant_id", "chat_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="America/Bogota")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    last_execution_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ScheduledTask id={self.id!r} tenant_id={self.tenant_id} status={self.status!r}>"


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------

class AuditLog(Base):
    """Registro de auditoría — scoped por tenant."""
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_log_tenant_chat", "tenant_id", "chat_id", "timestamp_utc"),
        Index("idx_audit_log_timestamp", "timestamp_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_invoked: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tool_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} tenant_id={self.tenant_id} event={self.event_type!r}>"


# ---------------------------------------------------------------------------
# Configuración del agente
# ---------------------------------------------------------------------------

class AgentConfig(Base):
    """
    Configuración editable del agente — una fila por tenant.
    El orquestador la lee en cada request.
    """
    __tablename__ = "agent_config"
    __table_args__ = (
        Index("idx_agent_config_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False, default="openai/gpt-4o-mini")
    temperature: Mapped[float] = mapped_column(nullable=False, default=0.7)
    conversation_window: Mapped[int] = mapped_column(nullable=False, default=20)
    max_tool_cycles: Mapped[int] = mapped_column(nullable=False, default=5)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="agent_configs")

    def __repr__(self) -> str:
        return f"<AgentConfig id={self.id} tenant_id={self.tenant_id} model={self.model!r}>"


# ---------------------------------------------------------------------------
# Solicitudes de acceso
# ---------------------------------------------------------------------------

class AccessRequest(Base):
    """Solicitudes de acceso pendientes — scoped por tenant."""
    __tablename__ = "access_requests"
    __table_args__ = (
        Index("idx_access_requests_tenant_chat", "tenant_id", "chat_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<AccessRequest tenant_id={self.tenant_id} chat_id={self.chat_id} status={self.status!r}>"
