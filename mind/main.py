"""
Aplicación FastAPI principal de Mind by Versat.
Gestiona el ciclo de vida completo: DB, migraciones, bot, scheduler.
Requisitos: 10.1 - 10.8
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
    Ciclo de vida de la aplicación:
    Startup: config → DB → migraciones → bot webhook → scheduler
    Shutdown: scheduler → engine → webhook
    """
    # --- 1. Cargar y validar configuración ---
    try:
        from mind.config import settings
    except SystemExit:
        logger.critical("Falló la validación de configuración. Abortando.")
        sys.exit(1)

    logger.info("Iniciando Mind by Versat...")

    # --- 2. Inicializar base de datos ---
    from mind.db.base import init_db, get_engine
    init_db(settings.DATABASE_URL)
    engine = get_engine()

    # --- 3. Verificar conectividad y ejecutar migraciones ---
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

    # Ejecutar migraciones Alembic
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

    # --- 4. Inicializar bot de Telegram ---
    from mind.telegram.bot import init_bot, setup_webhook, send_text as _send_text
    bot_app = init_bot(settings.TELEGRAM_BOT_TOKEN)
    await bot_app.initialize()

    try:
        await setup_webhook(settings.TELEGRAM_WEBHOOK_URL, settings.TELEGRAM_BOT_TOKEN)
    except Exception as exc:
        logger.warning("No se pudo registrar el webhook: %s. Continuando...", exc)

    # --- 5. Inicializar scheduler ---
    from mind.scheduler.manager import init_scheduler, set_bot_send_fn
    set_bot_send_fn(_send_text)
    sched = init_scheduler(settings.DATABASE_URL_SYNC)
    sched.start()
    logger.info("Scheduler iniciado.")

    logger.info("Mind by Versat listo en puerto %s.", settings.PORT)
    yield

    # --- Shutdown ---
    logger.info("Apagando Mind by Versat...")
    sched.shutdown(wait=False)

    try:
        from mind.telegram.bot import get_application
        tg_app = get_application()
        await tg_app.bot.delete_webhook()
        await tg_app.shutdown()
    except Exception:
        pass

    await engine.dispose()
    logger.info("Apagado completado.")


# Crear aplicación FastAPI
app = FastAPI(
    title="Mind by Versat",
    description="Agente de IA para miembros de juntas directivas",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS para desarrollo local del panel React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar API del panel de administración
from mind.admin.routes import router as admin_router
app.include_router(admin_router)

# Servir assets estáticos del SPA de React
from pathlib import Path as _Path
_static_dir = _Path(__file__).parent / "admin" / "static"
if _static_dir.exists():
    app.mount("/admin/assets", StaticFiles(directory=str(_static_dir / "assets")), name="admin-assets")
    from mind.admin.spa import spa_router
    app.include_router(spa_router)


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    """
    Recibe updates de Telegram y los procesa de forma async.
    Siempre retorna 200 inmediatamente para no bloquear a Telegram.
    """
    try:
        data = await request.json()
        from mind.telegram.bot import process_update
        asyncio.create_task(process_update(data))
    except Exception as exc:
        logger.error("Error procesando webhook: %s", exc)
    return JSONResponse({"ok": True})


@app.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check: verifica conectividad con PostgreSQL.
    Retorna 200 si todo OK, 503 si PostgreSQL no está disponible.
    Requisito: 10.8
    """
    try:
        from mind.db.base import get_engine
        import sqlalchemy
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        return JSONResponse({"status": "ok"})
    except RuntimeError:
        # Engine no inicializado (antes del startup)
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
