"""
Aplicación FastAPI principal de Mind by Versat.
Multi-tenant: el lifespan carga todos los tenants activos, inicializa
un bot de Telegram por cada uno y registra sus webhooks.
El endpoint /webhook/{bot_token} enruta cada update al bot correcto.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:
      1. Validar configuración
      2. Inicializar DB (engine async)
      3. Verificar conectividad PostgreSQL
      4. Ejecutar migraciones Alembic
      5. Cargar todos los tenants activos
      6. Inicializar un bot por tenant + registrar webhooks
      7. Inicializar scheduler

    Shutdown:
      - Apagar scheduler
      - Apagar todos los bots y eliminar webhooks
      - Cerrar engine
    """
    # 1. Configuración
    try:
        from mind.config import settings
    except SystemExit:
        logger.critical("Falló la validación de configuración. Abortando.")
        sys.exit(1)

    logger.info("Iniciando Mind by Versat (multi-tenant)...")

    # 2. Inicializar base de datos
    from mind.db.base import init_db, get_engine
    init_db(settings.DATABASE_URL)
    engine = get_engine()

    # 3. Verificar conectividad PostgreSQL
    connected = False
    for attempt in range(5):
        try:
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            connected = True
            logger.info("Conexión a PostgreSQL establecida.")
            break
        except Exception as exc:
            logger.warning(
                "Intento %d/5 — PostgreSQL no disponible: %s", attempt + 1, type(exc).__name__
            )
            if attempt < 4:
                await asyncio.sleep(6)

    if not connected:
        logger.critical("No se pudo conectar a PostgreSQL tras 5 intentos. Abortando.")
        sys.exit(1)

    # 4. Ejecutar migraciones Alembic
    try:
        import os as _os
        migration_env = _os.environ.copy()
        migration_env["DATABASE_URL_SYNC"] = settings.DATABASE_URL_SYNC
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            timeout=60,
            env=migration_env,
        )
        if result.returncode != 0:
            logger.critical("Error en migraciones Alembic:\n%s", result.stderr)
            sys.exit(1)
        logger.info("Migraciones aplicadas correctamente.")
    except Exception as exc:
        logger.critical("Error ejecutando migraciones: %s", exc)
        sys.exit(1)

    # 5. Cargar todos los tenants activos
    from mind.db.base import _session_factory
    from mind.tenants.resolver import load_all_active_tenants

    async with _session_factory() as session:
        tenants = await load_all_active_tenants(session)

    if not tenants:
        logger.warning(
            "No hay tenants activos en la BD. "
            "El bot no responderá hasta que se cree al menos uno."
        )

    # 6. Inicializar un bot por tenant
    from mind.telegram.bot import init_bot, setup_webhook

    for tenant in tenants:
        try:
            bot_app = init_bot(tenant.bot_token)
            await bot_app.initialize()
            await setup_webhook(tenant.webhook_url, tenant.bot_token)
            logger.info("Bot inicializado para tenant '%s'.", tenant.slug)
        except Exception as exc:
            logger.warning(
                "No se pudo inicializar bot para tenant '%s': %s", tenant.slug, exc
            )

    # 7. Inicializar scheduler
    from mind.scheduler.manager import init_scheduler
    sched = init_scheduler(settings.DATABASE_URL_SYNC)
    sched.start()
    logger.info("Scheduler iniciado.")

    logger.info("Mind by Versat listo en puerto %s. Tenants activos: %s",
                settings.PORT, [t.slug for t in tenants])
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Apagando Mind by Versat...")
    sched.shutdown(wait=False)

    from mind.telegram.bot import get_all_applications, teardown_bot
    for token in list(get_all_applications().keys()):
        await teardown_bot(token)

    await engine.dispose()
    logger.info("Apagado completado.")


# ── Aplicación FastAPI ────────────────────────────────────────────────────────
app = FastAPI(
    title="Mind by Versat",
    description="Agente de IA multi-tenant para miembros de juntas directivas",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Panel de administración
from mind.admin.routes import router as admin_router
app.include_router(admin_router)

# Servir assets del SPA React
from pathlib import Path as _Path
_static_dir = _Path(__file__).parent / "admin" / "static"
if _static_dir.exists():
    app.mount(
        "/admin/assets",
        StaticFiles(directory=str(_static_dir / "assets")),
        name="admin-assets",
    )
    from mind.admin.spa import spa_router
    app.include_router(spa_router)


# ── Webhook multi-tenant ──────────────────────────────────────────────────────

@app.post("/webhook/{bot_token}")
async def webhook(bot_token: str, request: Request) -> JSONResponse:
    """
    Recibe updates de Telegram para el bot identificado por bot_token.
    Telegram llama a este endpoint porque el webhook se registró como
    https://<host>/webhook/<bot_token>.
    """
    from mind.tenants.resolver import resolve_by_token
    from mind.telegram.bot import process_update

    tenant = resolve_by_token(bot_token)
    if tenant is None:
        # Token desconocido — ignorar silenciosamente (no exponer info)
        return JSONResponse({"ok": True})

    try:
        data = await request.json()
        asyncio.create_task(process_update(data, bot_token))
    except Exception as exc:
        logger.error("Error procesando webhook bot=...%s: %s", bot_token[-6:], exc)

    return JSONResponse({"ok": True})


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check() -> JSONResponse:
    """Verifica conectividad con PostgreSQL y número de tenants activos."""
    try:
        from mind.db.base import get_engine
        import sqlalchemy
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))

        from mind.tenants.resolver import get_all_cached
        active_tenants = len(get_all_cached())

        return JSONResponse({"status": "ok", "active_tenants": active_tenants})
    except RuntimeError:
        return JSONResponse({"status": "degraded"}, status_code=503)
    except Exception as exc:
        logger.warning("Health check fallido: %s", type(exc).__name__)
        return JSONResponse({"status": "degraded"}, status_code=503)


if __name__ == "__main__":
    import os
    import uvicorn
    from mind.config import settings
    port = int(os.environ.get("PORT", settings.PORT))
    uvicorn.run("mind.main:app", host="0.0.0.0", port=port, reload=False)
