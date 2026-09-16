from __future__ import annotations
import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    is_valid: bool
    error_field: str | None = None
    error_message: str | None = None

def validate_date_params(start: str, end: str) -> ValidationResult:
    try:
        ds = date.fromisoformat(start)
    except (ValueError, TypeError):
        return ValidationResult(False, "fecha_inicio", f"Formato inválido: {start!r}. Use YYYY-MM-DD.")
    try:
        de = date.fromisoformat(end)
    except (ValueError, TypeError):
        return ValidationResult(False, "fecha_fin", f"Formato inválido: {end!r}. Use YYYY-MM-DD.")
    if de < ds:
        return ValidationResult(False, "fecha_fin", "fecha_fin no puede ser anterior a fecha_inicio.")
    return ValidationResult(True)

def _year_range():
    y = datetime.now().year
    return f"{y}-01-01", f"{y}-12-31"

async def consultar_ventas(fecha_inicio: str | None = None, fecha_fin: str | None = None):
    if not fecha_inicio or not fecha_fin:
        fecha_inicio, fecha_fin = _year_range()
    v = validate_date_params(fecha_inicio, fecha_fin)
    if not v.is_valid:
        return {"error": True, "campo": v.error_field, "mensaje": v.error_message}
    try:
        from mind.data.connectors import get_sales_summary
        data = await asyncio.to_thread(get_sales_summary, date.fromisoformat(fecha_inicio), date.fromisoformat(fecha_fin))
        return {"error": False, "periodo": {"desde": fecha_inicio, "hasta": fecha_fin}, "resumen_mensual": data, "total_meses": len(data)}
    except Exception as exc:
        logger.error("Error en consultar_ventas: %s\n%s", exc, traceback.format_exc())
        return {"error": True, "mensaje": f"{type(exc).__name__}: {exc}"}

async def consultar_ventas_detalle(fecha_inicio: str, fecha_fin: str):
    v = validate_date_params(fecha_inicio, fecha_fin)
    if not v.is_valid:
        return {"error": True, "campo": v.error_field, "mensaje": v.error_message}
    try:
        from mind.data.connectors import get_sales
        data = await asyncio.to_thread(get_sales, date.fromisoformat(fecha_inicio), date.fromisoformat(fecha_fin))
        return {"error": False, "periodo": {"desde": fecha_inicio, "hasta": fecha_fin}, "datos": data[:200], "total_registros": len(data)}
    except Exception as exc:
        logger.error("Error en consultar_ventas_detalle: %s\n%s", exc, traceback.format_exc())
        return {"error": True, "mensaje": f"{type(exc).__name__}: {exc}"}

async def consultar_indicadores():
    fi, ff = _year_range()
    try:
        from mind.data.connectors import get_sales_summary, get_cuentas_por_pagar
        ventas, cxp = await asyncio.gather(
            asyncio.to_thread(get_sales_summary, date.fromisoformat(fi), date.fromisoformat(ff)),
            asyncio.to_thread(get_cuentas_por_pagar, date.fromisoformat(fi), date.fromisoformat(ff)),
        )
        tv = sum(r.get("total_ventas") or 0 for r in ventas)
        tc = sum(r.get("total_costo") or 0 for r in ventas)
        tx = sum(r.get("num_transacciones") or 0 for r in ventas)
        mg = round((tv - tc) / tv * 100, 1) if tv else 0
        deu = round(sum(r.get("deuda") or 0 for r in cxp), 2)
        return {"error": False, "año": fi[:4], "indicadores": [
            {"indicador": "Ventas Año Actual", "valor": round(tv, 2), "unidad": "COP"},
            {"indicador": "Costo Total", "valor": round(tc, 2), "unidad": "COP"},
            {"indicador": "Margen Bruto", "valor": mg, "unidad": "%"},
            {"indicador": "Total Transacciones", "valor": tx, "unidad": "transacciones"},
            {"indicador": "Cuentas por Pagar", "valor": deu, "unidad": "COP"}]}
    except Exception as exc:
        logger.error("Error en consultar_indicadores: %s\n%s", exc, traceback.format_exc())
        return {"error": True, "mensaje": f"{type(exc).__name__}: {exc}"}

async def consultar_finanzas(fecha_inicio: str | None = None, fecha_fin: str | None = None):
    if not fecha_inicio or not fecha_fin:
        fecha_inicio, fecha_fin = _year_range()
    v = validate_date_params(fecha_inicio, fecha_fin)
    if not v.is_valid:
        return {"error": True, "campo": v.error_field, "mensaje": v.error_message}
    try:
        from mind.data.connectors import get_cuentas_por_pagar, get_abonos, get_cuadre_caja
        ds, de = date.fromisoformat(fecha_inicio), date.fromisoformat(fecha_fin)
        cxp, ab, cj = await asyncio.gather(
            asyncio.to_thread(get_cuentas_por_pagar, ds, de),
            asyncio.to_thread(get_abonos, ds, de),
            asyncio.to_thread(get_cuadre_caja, ds, de))
        return {"error": False, "periodo": {"desde": fecha_inicio, "hasta": fecha_fin},
                "resumen": {"total_cuentas_por_pagar": round(sum(r.get("deuda") or 0 for r in cxp), 2),
                            "total_abonos_recibidos": round(sum(r.get("valor") or 0 for r in ab), 2),
                            "total_movimientos_caja": round(sum(r.get("valor") or 0 for r in cj), 2)},
                "cuentas_por_pagar": cxp[:50], "abonos": ab[:50], "caja": cj[:50]}
    except Exception as exc:
        logger.error("Error en consultar_finanzas: %s\n%s", exc, traceback.format_exc())
        return {"error": True, "mensaje": f"{type(exc).__name__}: {exc}"}

async def consultar_productos(filtro: str = ""):
    try:
        from mind.data.connectors import get_productos
        data = await asyncio.to_thread(get_productos, filtro)
        return {"error": False, "productos": data, "total": len(data)}
    except Exception as exc:
        logger.error("Error en consultar_productos: %s\n%s", exc, traceback.format_exc())
        return {"error": True, "mensaje": f"{type(exc).__name__}: {exc}"}

async def consultar_cxp(fecha_inicio: str | None = None, fecha_fin: str | None = None):
    if not fecha_inicio or not fecha_fin:
        fecha_inicio, fecha_fin = _year_range()
    v = validate_date_params(fecha_inicio, fecha_fin)
    if not v.is_valid:
        return {"error": True, "campo": v.error_field, "mensaje": v.error_message}
    try:
        from mind.data.connectors import get_cuentas_por_pagar
        data = await asyncio.to_thread(get_cuentas_por_pagar, date.fromisoformat(fecha_inicio), date.fromisoformat(fecha_fin))
        return {"error": False, "periodo": {"desde": fecha_inicio, "hasta": fecha_fin},
                "total_deuda": round(sum(r.get("deuda") or 0 for r in data), 2),
                "registros": data[:100], "total_registros": len(data)}
    except Exception as exc:
        logger.error("Error en consultar_cxp: %s\n%s", exc, traceback.format_exc())
        return {"error": True, "mensaje": f"{type(exc).__name__}: {exc}"}
