"""
Motor de base de datos SQLAlchemy async para Mind by Versat.
Requisitos: 5.8, 10.4
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Clase base para todos los modelos ORM."""
    pass


def create_engine_and_session(database_url: str):
    """
    Crea el engine async y el sessionmaker.
    Separado de la instanciación global para facilitar el testing.
    """
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,       # verifica conexión antes de usarla
        pool_size=5,
        max_overflow=10,
        connect_args={
            "statement_cache_size": 0,  # necesario para asyncpg + Alembic
            "command_timeout": 30,      # timeout de 30 s para consultas de datos
        },
    )
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return engine, session_factory


# Instancias globales — se inicializan en main.py lifespan
_engine = None
_session_factory = None


def init_db(database_url: str) -> None:
    """Inicializa el engine global. Llamar desde lifespan de FastAPI."""
    global _engine, _session_factory
    _engine, _session_factory = create_engine_and_session(database_url)


def get_engine():
    """Retorna el engine global. Debe haberse llamado init_db() antes."""
    if _engine is None:
        raise RuntimeError("DB engine no inicializado. Llama a init_db() primero.")
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency de FastAPI / generador de sesión async.
    Uso: session: AsyncSession = Depends(get_session)
    """
    if _session_factory is None:
        raise RuntimeError("DB session factory no inicializada. Llama a init_db() primero.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
