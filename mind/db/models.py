"""
Modelos ORM de Mind by Versat — SQLAlchemy 2.x.
Requisitos: 2.4, 2.5, 4.1, 4.4, 7.2, 8.1, 8.2
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mind.db.base import Base


class Role(Base):
    """Roles del sistema (board_member, admin, etc.)."""
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    users: Mapped[list[User]] = relationship("User", back_populates="role")
    permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name!r}>"


class RolePermission(Base):
    """Permisos asociados a un rol (relación N:M aplanada)."""
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_name: Mapped[str] = mapped_column(Text, primary_key=True)

    # Relación
    role: Mapped[Role] = relationship("Role", back_populates="permissions")

    def __repr__(self) -> str:
        return f"<RolePermission role_id={self.role_id} permission={self.permission_name!r}>"


class User(Base):
    """Usuarios autorizados para usar Mind (whitelist)."""
    __tablename__ = "users"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
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

    # Relación
    role: Mapped[Role] = relationship("Role", back_populates="users")

    def __repr__(self) -> str:
        return f"<User chat_id={self.chat_id} role_id={self.role_id} active={self.is_active}>"


class ConversationMessage(Base):
    """Historial de conversación por chat_id."""
    __tablename__ = "conversation_history"
    __table_args__ = (
        Index("idx_conv_history_chat_id", "chat_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)   # 'user' | 'assistant' | 'tool'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<ConversationMessage id={self.id} chat_id={self.chat_id} role={self.role!r}>"


class ScheduledTask(Base):
    """Tareas programadas del scheduler."""
    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        Index("idx_scheduled_tasks_chat_id", "chat_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)   # UUID generado por la app
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, default="America/Bogota"
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active"
    )  # 'active' | 'inactive'
    last_execution_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ScheduledTask id={self.id!r} chat_id={self.chat_id} status={self.status!r}>"


class AuditLog(Base):
    """Registro de auditoría de todas las interacciones."""
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_log_chat_id", "chat_id", "timestamp_utc"),
        Index("idx_audit_log_timestamp", "timestamp_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # 'interaction' | 'unauthorized' | 'tool_failure' | 'scheduler'
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
    status: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # 'success' | 'error'
    error_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} event={self.event_type!r} status={self.status!r}>"


class AgentConfig(Base):
    """
    Configuración editable del agente: system prompt, modelo, parámetros.
    Solo existe una fila (id=1). El orquestador la lee en cada request.
    """
    __tablename__ = "agent_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False, default="openai/gpt-4o-mini")
    temperature: Mapped[float] = mapped_column(nullable=False, default=0.7)
    conversation_window: Mapped[int] = mapped_column(nullable=False, default=20)
    max_tool_cycles: Mapped[int] = mapped_column(nullable=False, default=5)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<AgentConfig id={self.id} model={self.model!r}>"


class AccessRequest(Base):
    """Solicitudes de acceso pendientes de aprobación."""
    __tablename__ = "access_requests"
    __table_args__ = (
        Index("idx_access_requests_chat_id", "chat_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<AccessRequest chat_id={self.chat_id} status={self.status!r}>"
