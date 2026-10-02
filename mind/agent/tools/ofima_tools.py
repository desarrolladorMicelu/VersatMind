"""
Herramientas OFIMA adicionales para el agente (catálogo de precios, stock,
gangazos, ventas recientes, IMEI, historial de cliente, proveedores, sync).

Multi-tenant: el conector resuelve las credenciales del tenant activo.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

logger = logging.getLogger(__name__)


def _fail(where: str, exc: Exception) -> dict[str, Any]:
    logger.error("Error en %s: %s\n%s", where, exc, traceback.format_exc())
    return {"error": True, "mensaje": f"{type(exc).__name__}: {exc}"}


async def catalogo_precios(filtro: str = "", limite: int = 200) -> dict[str, Any]:
    """Catálogo de productos con su precio, marca/categoría y disponibilidad."""
    try:
        from mind.data.connectors import get_catalogo_precios
        data = await asyncio.to_thread(get_catalogo_precios, filtro, limite)
        return {"error": False, "productos": data, "total": len(data)}
    except Exception as exc:
        return _fail("catalogo_precios", exc)


async def stock_celulares() -> dict[str, Any]:
    """Cantidad disponible de celulares por referencia y bodega."""
    try:
        from mind.data.connectors import get_stock_celulares
        data = await asyncio.to_thread(get_stock_celulares)
        return {"error": False, "stock": data, "total_referencias": len(data)}
    except Exception as exc:
        return _fail("stock_celulares", exc)


async def gangazos() -> dict[str, Any]:
    """Equipos de servicio técnico listos para venta como gangazo."""
    try:
        from mind.data.connectors import get_gangazos
        data = await asyncio.to_thread(get_gangazos)
        return {"error": False, "gangazos": data, "total": len(data)}
    except Exception as exc:
        return _fail("gangazos", exc)


async def ventas_recientes(dias: int = 90, limite: int = 1000) -> dict[str, Any]:
    """Ventas de los últimos N días (qué, cuándo, quién, a qué cliente)."""
    try:
        from mind.data.connectors import get_ventas_recientes
        data = await asyncio.to_thread(get_ventas_recientes, dias, limite)
        return {"error": False, "dias": dias, "ventas": data, "total_registros": len(data)}
    except Exception as exc:
        return _fail("ventas_recientes", exc)


async def inventario_bodega(bodega: str, limite: int = 1000) -> dict[str, Any]:
    """Inventario físico (IMEI a IMEI) de una bodega específica."""
    try:
        from mind.data.connectors import get_inventario_bodega
        data = await asyncio.to_thread(get_inventario_bodega, bodega, limite)
        return {"error": False, "bodega": bodega, "items": data, "total": len(data)}
    except Exception as exc:
        return _fail("inventario_bodega", exc)


async def validar_imei(imei: str) -> dict[str, Any]:
    """Verifica si un IMEI/serie existe en Ofima, en qué bodega y qué producto es."""
    try:
        from mind.data.connectors import get_imei
        data = await asyncio.to_thread(get_imei, imei)
        return {"error": False, "imei": imei, "encontrado": bool(data), "resultados": data}
    except Exception as exc:
        return _fail("validar_imei", exc)


async def historial_cliente(nit: str, limite: int = 200) -> dict[str, Any]:
    """Historial de compras de un cliente por NIT/cédula."""
    try:
        from mind.data.connectors import get_historial_cliente
        data = await asyncio.to_thread(get_historial_cliente, nit, limite)
        return {"error": False, "nit": nit, "compras": data, "total": len(data)}
    except Exception as exc:
        return _fail("historial_cliente", exc)


async def buscar_cliente(nit: str) -> dict[str, Any]:
    """Busca si un NIT/cédula existe como cliente en Ofima."""
    try:
        from mind.data.connectors import get_cliente_por_nit
        data = await asyncio.to_thread(get_cliente_por_nit, nit)
        return {"error": False, "nit": nit, "clientes": data, "total": len(data)}
    except Exception as exc:
        return _fail("buscar_cliente", exc)


async def direccion_proveedor(proveedor: str) -> dict[str, Any]:
    """Obtiene la dirección registrada de un proveedor por nombre."""
    try:
        from mind.data.connectors import get_direccion_proveedor
        data = await asyncio.to_thread(get_direccion_proveedor, proveedor)
        return {"error": False, "proveedor": proveedor, "resultados": data}
    except Exception as exc:
        return _fail("direccion_proveedor", exc)


async def estado_sincronizacion_clientes() -> dict[str, Any]:
    """Estado de sincronización de clientes entre el sistema de ventas y Ofima."""
    try:
        from mind.data.connectors import get_estado_sync_clientes
        data = await asyncio.to_thread(get_estado_sync_clientes)
        return {"error": False, "sincronizacion": data[0] if data else {}}
    except Exception as exc:
        return _fail("estado_sincronizacion_clientes", exc)


async def inventario_activos(limite: int = 2000) -> dict[str, Any]:
    """Equipos activos en inventario (todas las líneas) con su descripción."""
    try:
        from mind.data.connectors import get_inventario_activos
        data = await asyncio.to_thread(get_inventario_activos, limite)
        return {"error": False, "items": data, "total": len(data)}
    except Exception as exc:
        return _fail("inventario_activos", exc)


async def cliente_completo(nit: str) -> dict[str, Any]:
    """Datos completos de un cliente por NIT (dirección, teléfonos, email) para documentos/firmas."""
    try:
        from mind.data.connectors import get_cliente_completo
        data = await asyncio.to_thread(get_cliente_completo, nit)
        return {"error": False, "nit": nit, "encontrado": bool(data), "cliente": data[0] if data else None}
    except Exception as exc:
        return _fail("cliente_completo", exc)


async def factura_reciente_cliente(nit: str) -> dict[str, Any]:
    """Factura más reciente de un cliente (tipo y número) para asociar pedidos."""
    try:
        from mind.data.connectors import get_factura_reciente
        data = await asyncio.to_thread(get_factura_reciente, nit)
        return {"error": False, "nit": nit, "encontrada": bool(data), "factura": data[0] if data else None}
    except Exception as exc:
        return _fail("factura_reciente_cliente", exc)


async def medios_pago() -> dict[str, Any]:
    """Lista de medios de pago / bancos registrados en Ofima."""
    try:
        from mind.data.connectors import get_medios_pago
        data = await asyncio.to_thread(get_medios_pago)
        return {"error": False, "medios_pago": data, "total": len(data)}
    except Exception as exc:
        return _fail("medios_pago", exc)


async def movimientos_contables(fecha_inicio: str, fecha_fin: str, limite: int = 500) -> dict[str, Any]:
    """Movimientos contables/caja por rango de fechas (tercero, ciudad, crédito/débito)."""
    from datetime import date
    try:
        ds = date.fromisoformat(fecha_inicio)
        de = date.fromisoformat(fecha_fin)
    except (ValueError, TypeError):
        return {"error": True, "mensaje": "Fechas inválidas. Usa YYYY-MM-DD."}
    if de < ds:
        return {"error": True, "mensaje": "fecha_fin no puede ser anterior a fecha_inicio."}
    try:
        from mind.data.connectors import get_movimientos_contables
        data = await asyncio.to_thread(get_movimientos_contables, ds, de, limite)
        return {"error": False, "periodo": {"desde": fecha_inicio, "hasta": fecha_fin},
                "movimientos": data, "total_registros": len(data)}
    except Exception as exc:
        return _fail("movimientos_contables", exc)
