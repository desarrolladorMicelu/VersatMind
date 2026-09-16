from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Callable, Awaitable
from mind.auth.authorization import Permission

class PermissionDeniedError(Exception): pass
class ToolNotFoundError(Exception): pass
class ToolValidationError(Exception): pass

@dataclass
class ToolDefinition:
    fn: Callable[..., Awaitable[dict]]
    permission: Permission
    schema: dict

TOOL_REGISTRY: dict[str, ToolDefinition] = {}

def get_tool_schemas():
    return [{"type": "function", "function": d.schema} for d in TOOL_REGISTRY.values()]

async def dispatch(tool_name: str, params: dict, user_permissions: frozenset[str]):
    defn = TOOL_REGISTRY.get(tool_name)
    if defn is None:
        raise ToolNotFoundError(f"Herramienta desconocida: {tool_name!r}")
    if defn.permission.value not in user_permissions:
        raise PermissionDeniedError(f"Sin permiso para ejecutar {tool_name!r}")
    try:
        result = await defn.fn(**params)
        return json.dumps(result, ensure_ascii=False, default=str)
    except PermissionDeniedError:
        raise
    except Exception as exc:
        raise ToolValidationError(f"Error ejecutando {tool_name!r}: {exc}") from exc

def _register_all_tools():
    from mind.agent.tools.data_tools import (consultar_ventas, consultar_ventas_detalle, consultar_indicadores,
                                              consultar_finanzas, consultar_productos, consultar_cxp)
    from mind.agent.tools.report_tools import generar_informe
    from mind.agent.tools.scheduler_tools import (crear_tarea_programada, listar_tareas, eliminar_tarea, modificar_tarea)

    TOOL_REGISTRY["consultar_ventas"] = ToolDefinition(fn=consultar_ventas, permission=Permission.READ_SALES,
        schema={"name": "consultar_ventas", "description": "Resumen mensual de ventas OFIMA. Sin período usa año actual.",
                "parameters": {"type": "object", "properties": {
                    "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                    "fecha_fin": {"type": "string", "description": "YYYY-MM-DD (opcional)"}}, "required": []}})
    TOOL_REGISTRY["consultar_ventas_detalle"] = ToolDefinition(fn=consultar_ventas_detalle, permission=Permission.READ_SALES,
        schema={"name": "consultar_ventas_detalle", "description": "Detalle transaccional de ventas OFIMA.",
                "parameters": {"type": "object", "properties": {
                    "fecha_inicio": {"type": "string"}, "fecha_fin": {"type": "string"}}, "required": ["fecha_inicio", "fecha_fin"]}})
    TOOL_REGISTRY["consultar_indicadores"] = ToolDefinition(fn=consultar_indicadores, permission=Permission.READ_KPI,
        schema={"name": "consultar_indicadores", "description": "KPIs del año actual: ventas, margen, CxP.",
                "parameters": {"type": "object", "properties": {}, "required": []}})
    TOOL_REGISTRY["consultar_finanzas"] = ToolDefinition(fn=consultar_finanzas, permission=Permission.READ_FINANCE,
        schema={"name": "consultar_finanzas", "description": "Estado financiero OFIMA: CxP, abonos y caja.",
                "parameters": {"type": "object", "properties": {
                    "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                    "fecha_fin": {"type": "string", "description": "YYYY-MM-DD (opcional)"}}, "required": []}})
    TOOL_REGISTRY["consultar_productos"] = ToolDefinition(fn=consultar_productos, permission=Permission.READ_SALES,
        schema={"name": "consultar_productos", "description": "Catálogo de productos OFIMA.",
                "parameters": {"type": "object", "properties": {
                    "filtro": {"type": "string", "description": "Filtro por descripción (opcional)"}}, "required": []}})
    TOOL_REGISTRY["consultar_cxp"] = ToolDefinition(fn=consultar_cxp, permission=Permission.READ_FINANCE,
        schema={"name": "consultar_cxp", "description": "Cuentas por pagar OFIMA con total de deuda.",
                "parameters": {"type": "object", "properties": {
                    "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                    "fecha_fin": {"type": "string", "description": "YYYY-MM-DD (opcional)"}}, "required": []}})
    TOOL_REGISTRY["generar_informe"] = ToolDefinition(fn=generar_informe, permission=Permission.GENERATE_REPORT,
        schema={"name": "generar_informe", "description": "Genera informe PDF o Excel con datos OFIMA.",
                "parameters": {"type": "object", "properties": {
                    "tipo": {"type": "string", "enum": ["ventas", "finanzas", "indicadores"]},
                    "formato": {"type": "string", "enum": ["pdf", "excel"]},
                    "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                    "fecha_fin": {"type": "string", "description": "YYYY-MM-DD (opcional)"}}, "required": ["tipo", "formato"]}})
    TOOL_REGISTRY["crear_tarea_programada"] = ToolDefinition(fn=crear_tarea_programada, permission=Permission.MANAGE_TASKS,
        schema={"name": "crear_tarea_programada", "description": "Crea tarea programada recurrente.",
                "parameters": {"type": "object", "properties": {
                    "descripcion": {"type": "string"},
                    "expresion_cron": {"type": "string", "description": "Ej: '0 8 * * 1'"},
                    "chat_id": {"type": "integer"}}, "required": ["descripcion", "expresion_cron", "chat_id"]}})
    TOOL_REGISTRY["listar_tareas"] = ToolDefinition(fn=listar_tareas, permission=Permission.MANAGE_TASKS,
        schema={"name": "listar_tareas", "description": "Lista tareas programadas activas.",
                "parameters": {"type": "object", "properties": {"chat_id": {"type": "integer"}}, "required": ["chat_id"]}})
    TOOL_REGISTRY["eliminar_tarea"] = ToolDefinition(fn=eliminar_tarea, permission=Permission.MANAGE_TASKS,
        schema={"name": "eliminar_tarea", "description": "Elimina tarea programada.",
                "parameters": {"type": "object", "properties": {
                    "task_id": {"type": "string"}, "chat_id": {"type": "integer"}}, "required": ["task_id", "chat_id"]}})
    TOOL_REGISTRY["modificar_tarea"] = ToolDefinition(fn=modificar_tarea, permission=Permission.MANAGE_TASKS,
        schema={"name": "modificar_tarea", "description": "Modifica tarea programada.",
                "parameters": {"type": "object", "properties": {
                    "task_id": {"type": "string"}, "chat_id": {"type": "integer"},
                    "nueva_descripcion": {"type": "string"}, "nueva_expresion_cron": {"type": "string"}},
                    "required": ["task_id", "chat_id"]}})

_register_all_tools()
