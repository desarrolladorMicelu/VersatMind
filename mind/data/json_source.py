"""
Conector de fuentes JSON (R2) con cache y consultas filtradas.

No se inyecta el archivo completo al LLM: cada tool recibe filtros, se
ejecutan en el servidor y se devuelven como máximo 50 filas compactas.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

CACHE_TTL_SECONDS = 300
MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50
DEFAULT_ROWS = 20

_CACHE: dict[tuple[int, str], tuple[float, str | None, list[dict]]] = {}
_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}


class JsonSourceError(ValueError):
    pass


def _source_config(tenant, kind: str) -> dict[str, Any]:
    if kind not in ("precios", "historial"):
        raise JsonSourceError("Fuente JSON inválida.")
    cfg = (getattr(tenant, "json_sources", None) or {}).get(kind) or {}
    url = str(cfg.get("url") or "").strip()
    if not cfg.get("is_active", True) or not url:
        raise JsonSourceError("La fuente JSON no está configurada o está inactiva.")
    if not url.startswith("https://"):
        raise JsonSourceError("La URL JSON debe usar HTTPS.")
    return {"url": url, "is_active": True}


def _validate_payload(kind: str, payload: Any) -> list[dict]:
    if not isinstance(payload, list) or (payload and not isinstance(payload[0], dict)):
        raise JsonSourceError("El JSON debe ser un arreglo de objetos.")
    required = {
        "precios": {"nombre", "codigo"},
        "historial": {"producto", "codigo", "fecha", "tipo_cambio"},
    }[kind]
    for item in payload[:20]:
        if not required.issubset(item.keys()):
            raise JsonSourceError(
                "El JSON no tiene el esquema esperado: faltan campos "
                + ", ".join(sorted(required))
            )
    return [row for row in payload if isinstance(row, dict)]


async def _fetch_json(url: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            size = int(response.headers.get("content-length") or 0)
            if size > MAX_BYTES or len(response.content) > MAX_BYTES:
                raise JsonSourceError("El JSON supera el tamaño máximo permitido (10 MB).")
            return response.json()
    except JsonSourceError:
        raise
    except Exception as exc:
        raise JsonSourceError(f"No se pudo leer el JSON: {exc}") from exc


async def load_source(tenant, kind: str, *, force: bool = False) -> list[dict]:
    cfg = _source_config(tenant, kind)
    key = (int(tenant.id), kind)
    cached = _CACHE.get(key)
    now = time.monotonic()
    if not force and cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[2]

    lock = _LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _CACHE.get(key)
        now = time.monotonic()
        if not force and cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[2]
        payload = await _fetch_json(cfg["url"])
        records = _validate_payload(kind, payload)
        _CACHE[key] = (time.monotonic(), None, records)
        return records


def clear_cache(tenant_id: int | None = None) -> None:
    if tenant_id is None:
        _CACHE.clear()
        return
    for key in list(_CACHE):
        if key[0] == tenant_id:
            _CACHE.pop(key, None)


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def _limit(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = DEFAULT_ROWS
    return max(1, min(n, MAX_ROWS))


def _price_row(row: dict) -> dict:
    first = row.get("posicion_1") or {}
    micelu = row.get("micelu") or {}
    return {
        "nombre": row.get("nombre"),
        "codigo": row.get("codigo"),
        "codigo_ofim": row.get("codigo_ofim"),
        "vendedor_1": first.get("vendedor"),
        "precio_1": first.get("precio"),
        "micelu_existe": micelu.get("existe"),
        "micelu_posicion": micelu.get("posicion"),
        "micelu_precio": micelu.get("precio"),
        "diferencia_vs_posicion1": micelu.get("diferencia_vs_posicion1"),
        "diferencia_porcentaje": micelu.get("diferencia_porcentaje"),
        "total_vendedores": row.get("total_vendedores"),
    }


def query_precios(records: list[dict], **filters) -> dict:
    codigo = str(filters.get("codigo") or "").strip().lower()
    codigo_ofim = str(filters.get("codigo_ofim") or "").strip().lower()
    nombre = str(filters.get("nombre_contiene") or "").strip().lower()
    vendedor = str(filters.get("vendedor") or "").strip().lower()
    solo_micelu = bool(filters.get("solo_con_micelu"))
    precio_min = _num(filters.get("precio_min"))
    precio_max = _num(filters.get("precio_max"))
    limit = _limit(filters.get("limit"))

    result = []
    for row in records:
        first = row.get("posicion_1") or {}
        micelu = row.get("micelu") or {}
        if codigo and str(row.get("codigo", "")).lower() != codigo:
            continue
        if codigo_ofim and codigo_ofim not in str(row.get("codigo_ofim", "")).lower():
            continue
        if nombre and nombre not in str(row.get("nombre", "")).lower():
            continue
        if vendedor and vendedor not in str(first.get("vendedor", "")).lower():
            continue
        if solo_micelu and not micelu.get("existe"):
            continue
        price = _num(first.get("precio_numerico")) or _num(first.get("precio"))
        if precio_min is not None and (price is None or price < precio_min):
            continue
        if precio_max is not None and (price is None or price > precio_max):
            continue
        result.append(row)

    result.sort(key=lambda r: (
        _num((r.get("micelu") or {}).get("diferencia_porcentaje")) is None,
        -abs(_num((r.get("micelu") or {}).get("diferencia_porcentaje")) or 0),
    ))
    return {
        "total": len(result),
        "mostrados": min(len(result), limit),
        "items": [_price_row(r) for r in result[:limit]],
    }


def _history_row(row: dict) -> dict:
    return {
        "producto": row.get("producto"),
        "codigo": row.get("codigo"),
        "fecha": row.get("fecha"),
        "tipo_cambio": row.get("tipo_cambio"),
        "posicion_1_anterior": row.get("posicion_1_anterior"),
        "posicion_1_nuevo": row.get("posicion_1_nuevo"),
        "micelu_posicion_anterior": row.get("micelu_posicion_anterior"),
        "micelu_posicion_nuevo": row.get("micelu_posicion_nuevo"),
        "micelu_precio_anterior": row.get("micelu_precio_anterior"),
        "micelu_precio_nuevo": row.get("micelu_precio_nuevo"),
    }


def query_historial(records: list[dict], **filters) -> dict:
    codigo = str(filters.get("codigo") or "").strip().lower()
    producto = str(filters.get("producto_contiene") or "").strip().lower()
    tipo = str(filters.get("tipo_cambio") or "").strip().lower()
    desde = str(filters.get("desde") or "").strip()
    hasta = str(filters.get("hasta") or "").strip()
    limit = _limit(filters.get("limit"))

    result = []
    for row in records:
        if codigo and str(row.get("codigo", "")).lower() != codigo:
            continue
        if producto and producto not in str(row.get("producto", "")).lower():
            continue
        if tipo and tipo not in str(row.get("tipo_cambio", "")).lower():
            continue
        fecha = str(row.get("fecha", ""))
        if desde and fecha < desde:
            continue
        if hasta and fecha > hasta:
            continue
        result.append(row)
    result.sort(key=lambda r: str(r.get("fecha", "")), reverse=True)
    return {
        "total": len(result),
        "mostrados": min(len(result), limit),
        "items": [_history_row(r) for r in result[:limit]],
    }


def summary_historial(records: list[dict]) -> dict:
    tipos: dict[str, int] = {}
    productos = set()
    fechas = []
    for row in records:
        tipo = str(row.get("tipo_cambio") or "Sin tipo")
        tipos[tipo] = tipos.get(tipo, 0) + 1
        productos.add(str(row.get("codigo") or row.get("producto") or ""))
        if row.get("fecha"):
            fechas.append(str(row["fecha"]))
    return {
        "total_cambios": len(records),
        "productos_distintos": len([p for p in productos if p]),
        "tipos": [{"tipo": k, "cantidad": v} for k, v in sorted(tipos.items(), key=lambda x: -x[1])],
        "desde": min(fechas) if fechas else None,
        "hasta": max(fechas) if fechas else None,
    }


def summary_precios(records: list[dict]) -> dict:
    con_micelu = [r for r in records if (r.get("micelu") or {}).get("existe")]
    gaps = []
    for row in con_micelu:
        gap = _num((row.get("micelu") or {}).get("diferencia_porcentaje"))
        if gap is not None:
            gaps.append(gap)
    return {
        "total_productos": len(records),
        "con_micelu": len(con_micelu),
        "sin_micelu": len(records) - len(con_micelu),
        "brecha_promedio_porcentaje": round(sum(gaps) / len(gaps), 2) if gaps else None,
        "brecha_maxima_porcentaje": max(gaps) if gaps else None,
    }


async def validate_json_source(kind: str, url: str) -> dict:
    if kind not in ("precios", "historial"):
        raise JsonSourceError("Tipo de fuente inválido.")
    if not url.startswith("https://"):
        raise JsonSourceError("La URL JSON debe usar HTTPS.")
    payload = await _fetch_json(url)
    records = _validate_payload(kind, payload)
    return {"ok": True, "kind": kind, "count": len(records)}
