"""
Sirve el SPA de React desde FastAPI.
GET /admin/* → devuelve el index.html del build de React.
Los assets estáticos se sirven desde /admin/assets/*.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"

spa_router = APIRouter()


def get_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@spa_router.get("/admin/login")
@spa_router.get("/admin/agente")
@spa_router.get("/admin/usuarios")
@spa_router.get("/admin/accesos")
@spa_router.get("/admin/roles")
@spa_router.get("/admin/tareas")
@spa_router.get("/admin/historial")
@spa_router.get("/admin/auditoria")
@spa_router.get("/admin/")
@spa_router.get("/admin")
async def serve_spa():
    return get_index()
