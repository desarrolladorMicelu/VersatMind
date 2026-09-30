"""
Sirve el SPA de React desde FastAPI.

- GET /admin y /admin/* → devuelve index.html del build de React, para que
  funcionen las rutas del cliente (refrescar, atrás/adelante, entrar directo
  a /admin/consumo, etc.).
- Los assets reales se sirven desde /admin/assets/* (StaticFiles) y nunca
  caen aquí; si un asset no existe, se responde 404 real (no index.html).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).parent / "static"

spa_router = APIRouter()


def get_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@spa_router.get("/admin")
@spa_router.get("/admin/")
async def serve_spa_root():
    return get_index()


@spa_router.get("/admin/{full_path:path}")
async def serve_spa(full_path: str):
    # No interceptar archivos estáticos: si no existen, debe ser 404 real.
    _, ext = os.path.splitext(full_path)
    if full_path == "assets" or full_path.startswith("assets/") or ext:
        raise HTTPException(status_code=404, detail="Not Found")
    return get_index()
