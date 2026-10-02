"""
Registro y dispatch de herramientas del agente.
Las tools disponibles son las mismas para todos los tenants;
el control de acceso es por permisos de rol (ya existente).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from mind.auth.authorization import Permission


class PermissionDeniedError(Exception):
    pass


class ToolNotFoundError(Exception):
    pass


class ToolValidationError(Exception):
    pass


@dataclass
class ToolDefinition:
    fn: Callable[..., Awaitable[dict]]
    permission: Permission
    schema: dict


TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def get_tool_schemas() -> list[dict]:
    return [{"type": "function", "function": d.schema} for d in TOOL_REGISTRY.values()]


async def dispatch(
    tool_name: str,
    params: dict,
    user_permissions: frozenset[str],
) -> str:
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


def _register_all_tools() -> None:
    from mind.agent.tools.data_tools import (
        consultar_ventas,
        consultar_ventas_detalle,
        consultar_indicadores,
        consultar_finanzas,
        consultar_productos,
        consultar_cxp,
    )
    from mind.agent.tools.ofima_tools import (
        catalogo_precios,
        stock_celulares,
        gangazos,
        ventas_recientes,
        inventario_bodega,
        validar_imei,
        historial_cliente,
        buscar_cliente,
        direccion_proveedor,
        estado_sincronizacion_clientes,
        inventario_activos,
        cliente_completo,
        factura_reciente_cliente,
        medios_pago,
        movimientos_contables,
    )
    from mind.agent.tools.report_tools import generar_informe
    from mind.agent.tools.scheduler_tools import (
        crear_tarea_programada,
        listar_tareas,
        eliminar_tarea,
        modificar_tarea,
    )
    from mind.agent.tools.external_db_tool import ejecutar_consulta
    from mind.agent.tools.sheets_tool import consultar_sheet
    from mind.agent.tools.alegra_tool import consultar_alegra
    from mind.agent.tools.report_tool import generar_informe_contable

    TOOL_REGISTRY["consultar_ventas"] = ToolDefinition(
        fn=consultar_ventas,
        permission=Permission.READ_SALES,
        schema={
            "name": "consultar_ventas",
            "description": "Resumen mensual de ventas OFIMA. Sin período usa año actual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                    "fecha_fin": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                },
                "required": [],
            },
        },
    )
    TOOL_REGISTRY["consultar_ventas_detalle"] = ToolDefinition(
        fn=consultar_ventas_detalle,
        permission=Permission.READ_SALES,
        schema={
            "name": "consultar_ventas_detalle",
            "description": "Detalle transaccional de ventas OFIMA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fecha_inicio": {"type": "string"},
                    "fecha_fin": {"type": "string"},
                },
                "required": ["fecha_inicio", "fecha_fin"],
            },
        },
    )
    TOOL_REGISTRY["consultar_indicadores"] = ToolDefinition(
        fn=consultar_indicadores,
        permission=Permission.READ_KPI,
        schema={
            "name": "consultar_indicadores",
            "description": "KPIs del año actual: ventas, margen, CxP.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    )
    TOOL_REGISTRY["consultar_finanzas"] = ToolDefinition(
        fn=consultar_finanzas,
        permission=Permission.READ_FINANCE,
        schema={
            "name": "consultar_finanzas",
            "description": "Estado financiero OFIMA: CxP, abonos y caja.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                    "fecha_fin": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                },
                "required": [],
            },
        },
    )
    TOOL_REGISTRY["consultar_productos"] = ToolDefinition(
        fn=consultar_productos,
        permission=Permission.READ_SALES,
        schema={
            "name": "consultar_productos",
            "description": "Catálogo de productos OFIMA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filtro": {"type": "string", "description": "Filtro por descripción (opcional)"},
                },
                "required": [],
            },
        },
    )
    TOOL_REGISTRY["consultar_cxp"] = ToolDefinition(
        fn=consultar_cxp,
        permission=Permission.READ_FINANCE,
        schema={
            "name": "consultar_cxp",
            "description": "Cuentas por pagar OFIMA con total de deuda.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                    "fecha_fin": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                },
                "required": [],
            },
        },
    )
    TOOL_REGISTRY["generar_informe"] = ToolDefinition(
        fn=generar_informe,
        permission=Permission.GENERATE_REPORT,
        schema={
            "name": "generar_informe",
            "description": "Genera informe PDF o Excel con datos OFIMA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": ["ventas", "finanzas", "indicadores"]},
                    "formato": {"type": "string", "enum": ["pdf", "excel"]},
                    "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                    "fecha_fin": {"type": "string", "description": "YYYY-MM-DD (opcional)"},
                },
                "required": ["tipo", "formato"],
            },
        },
    )
    # ── Consultas OFIMA adicionales ──────────────────────────────────────────
    TOOL_REGISTRY["catalogo_precios"] = ToolDefinition(
        fn=catalogo_precios,
        permission=Permission.READ_SALES,
        schema={
            "name": "catalogo_precios",
            "description": "Catálogo de productos con precio, marca/categoría, línea y disponibilidad (OFIMA). "
                           "Úsala para saber qué productos existen y a qué precio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filtro": {"type": "string", "description": "Texto a buscar en descripción o código (opcional)"},
                    "limite": {"type": "integer", "description": "Máximo de filas (default 200)"},
                },
                "required": [],
            },
        },
    )
    TOOL_REGISTRY["stock_celulares"] = ToolDefinition(
        fn=stock_celulares,
        permission=Permission.READ_SALES,
        schema={
            "name": "stock_celulares",
            "description": "Stock en tiempo real de celulares por referencia y bodega (OFIMA). "
                           "Úsala para saber cuántas unidades hay disponibles.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    )
    TOOL_REGISTRY["gangazos"] = ToolDefinition(
        fn=gangazos,
        permission=Permission.READ_SALES,
        schema={
            "name": "gangazos",
            "description": "Equipos de servicio técnico con estado 'C' disponibles para venta como gangazo, "
                           "con su nota/precio en XNOTA (OFIMA).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    )
    TOOL_REGISTRY["ventas_recientes"] = ToolDefinition(
        fn=ventas_recientes,
        permission=Permission.READ_SALES,
        schema={
            "name": "ventas_recientes",
            "description": "Ventas de los últimos N días: qué se vendió, cuándo, quién lo vendió y a qué cliente "
                           "(OFIMA, vista ventas_bodega, facturas FB/FM/FI).",
            "parameters": {
                "type": "object",
                "properties": {
                    "dias": {"type": "integer", "description": "Días hacia atrás (default 90)"},
                    "limite": {"type": "integer", "description": "Máximo de filas (default 1000)"},
                },
                "required": [],
            },
        },
    )
    TOOL_REGISTRY["inventario_bodega"] = ToolDefinition(
        fn=inventario_bodega,
        permission=Permission.READ_SALES,
        schema={
            "name": "inventario_bodega",
            "description": "Inventario físico exacto (serie/IMEI a serie) de una bodega, para arqueo (OFIMA).",
            "parameters": {
                "type": "object",
                "properties": {
                    "bodega": {"type": "string", "description": "Código de bodega. Ej: 'BM', 'BB', 'BCAL'"},
                    "limite": {"type": "integer", "description": "Máximo de filas (default 1000)"},
                },
                "required": ["bodega"],
            },
        },
    )
    TOOL_REGISTRY["validar_imei"] = ToolDefinition(
        fn=validar_imei,
        permission=Permission.READ_SALES,
        schema={
            "name": "validar_imei",
            "description": "Dado un IMEI/serie, indica si existe en Ofima, en qué bodega está y qué producto es.",
            "parameters": {
                "type": "object",
                "properties": {"imei": {"type": "string", "description": "IMEI o serie a validar"}},
                "required": ["imei"],
            },
        },
    )
    TOOL_REGISTRY["historial_cliente"] = ToolDefinition(
        fn=historial_cliente,
        permission=Permission.READ_SALES,
        schema={
            "name": "historial_cliente",
            "description": "Historial de compras de un cliente por NIT/cédula: qué compró, cuándo y cuánto pagó (OFIMA).",
            "parameters": {
                "type": "object",
                "properties": {
                    "nit": {"type": "string", "description": "NIT o cédula del cliente"},
                    "limite": {"type": "integer", "description": "Máximo de filas (default 200)"},
                },
                "required": ["nit"],
            },
        },
    )
    TOOL_REGISTRY["buscar_cliente"] = ToolDefinition(
        fn=buscar_cliente,
        permission=Permission.READ_SALES,
        schema={
            "name": "buscar_cliente",
            "description": "Busca si un NIT/cédula existe como cliente en Ofima y devuelve su nombre.",
            "parameters": {
                "type": "object",
                "properties": {"nit": {"type": "string", "description": "NIT o cédula a buscar"}},
                "required": ["nit"],
            },
        },
    )
    TOOL_REGISTRY["direccion_proveedor"] = ToolDefinition(
        fn=direccion_proveedor,
        permission=Permission.READ_FINANCE,
        schema={
            "name": "direccion_proveedor",
            "description": "Obtiene la dirección registrada de un proveedor por su nombre (OFIMA).",
            "parameters": {
                "type": "object",
                "properties": {"proveedor": {"type": "string", "description": "Nombre del proveedor"}},
                "required": ["proveedor"],
            },
        },
    )
    TOOL_REGISTRY["estado_sincronizacion_clientes"] = ToolDefinition(
        fn=estado_sincronizacion_clientes,
        permission=Permission.READ_FINANCE,
        schema={
            "name": "estado_sincronizacion_clientes",
            "description": "Estado de sincronización de clientes entre el sistema de ventas y Ofima "
                           "(pendientes y sincronizados en la última hora).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    )
    TOOL_REGISTRY["inventario_activos"] = ToolDefinition(
        fn=inventario_activos,
        permission=Permission.READ_SALES,
        schema={
            "name": "inventario_activos",
            "description": "Todos los equipos activos en inventario (series/IMEI) con su descripción (OFIMA). "
                           "Úsala para inventario consolidado de los equipos vigentes.",
            "parameters": {
                "type": "object",
                "properties": {"limite": {"type": "integer", "description": "Máximo de filas (default 2000)"}},
                "required": [],
            },
        },
    )
    TOOL_REGISTRY["cliente_completo"] = ToolDefinition(
        fn=cliente_completo,
        permission=Permission.READ_SALES,
        schema={
            "name": "cliente_completo",
            "description": "Datos completos de un cliente por NIT: dirección, teléfonos y email. "
                           "Úsala para firmar documentos (mandato, comodato, antifraude).",
            "parameters": {
                "type": "object",
                "properties": {"nit": {"type": "string", "description": "NIT o cédula del cliente"}},
                "required": ["nit"],
            },
        },
    )
    TOOL_REGISTRY["factura_reciente_cliente"] = ToolDefinition(
        fn=factura_reciente_cliente,
        permission=Permission.READ_SALES,
        schema={
            "name": "factura_reciente_cliente",
            "description": "Factura más reciente de un cliente (tipo y número) para asociar pedidos online.",
            "parameters": {
                "type": "object",
                "properties": {"nit": {"type": "string", "description": "NIT o cédula del cliente"}},
                "required": ["nit"],
            },
        },
    )
    TOOL_REGISTRY["medios_pago"] = ToolDefinition(
        fn=medios_pago,
        permission=Permission.READ_FINANCE,
        schema={
            "name": "medios_pago",
            "description": "Lista de medios de pago / bancos registrados en Ofima (efectivo, bancos, datáfono, etc.).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    )
    TOOL_REGISTRY["movimientos_contables"] = ToolDefinition(
        fn=movimientos_contables,
        permission=Permission.READ_FINANCE,
        schema={
            "name": "movimientos_contables",
            "description": "Movimientos contables/caja por rango de fechas, con tercero y ciudad "
                           "(crédito/débito). Úsala para flujo de caja y revisión contable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD"},
                    "fecha_fin": {"type": "string", "description": "YYYY-MM-DD (exclusivo)"},
                    "limite": {"type": "integer", "description": "Máximo de filas (default 500)"},
                },
                "required": ["fecha_inicio", "fecha_fin"],
            },
        },
    )
    TOOL_REGISTRY["crear_tarea_programada"] = ToolDefinition(
        fn=crear_tarea_programada,
        permission=Permission.MANAGE_TASKS,
        schema={
            "name": "crear_tarea_programada",
            "description": "Crea tarea programada recurrente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string"},
                    "expresion_cron": {"type": "string", "description": "Ej: '0 8 * * 1'"},
                    "chat_id": {"type": "integer"},
                },
                "required": ["descripcion", "expresion_cron", "chat_id"],
            },
        },
    )
    TOOL_REGISTRY["listar_tareas"] = ToolDefinition(
        fn=listar_tareas,
        permission=Permission.MANAGE_TASKS,
        schema={
            "name": "listar_tareas",
            "description": "Lista tareas programadas activas.",
            "parameters": {
                "type": "object",
                "properties": {"chat_id": {"type": "integer"}},
                "required": ["chat_id"],
            },
        },
    )
    TOOL_REGISTRY["eliminar_tarea"] = ToolDefinition(
        fn=eliminar_tarea,
        permission=Permission.MANAGE_TASKS,
        schema={
            "name": "eliminar_tarea",
            "description": "Elimina tarea programada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "chat_id": {"type": "integer"},
                },
                "required": ["task_id", "chat_id"],
            },
        },
    )
    TOOL_REGISTRY["modificar_tarea"] = ToolDefinition(
        fn=modificar_tarea,
        permission=Permission.MANAGE_TASKS,
        schema={
            "name": "modificar_tarea",
            "description": "Modifica tarea programada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "chat_id": {"type": "integer"},
                    "nueva_descripcion": {"type": "string"},
                    "nueva_expresion_cron": {"type": "string"},
                },
                "required": ["task_id", "chat_id"],
            },
        },
    )
    TOOL_REGISTRY["ejecutar_consulta"] = ToolDefinition(
        fn=ejecutar_consulta,
        permission=Permission.READ_EXTERNAL_DB,
        schema={
            "name": "ejecutar_consulta",
            "description": "Ejecuta una consulta SQL SELECT en la base de datos externa del cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "Consulta SQL SELECT. Ej: SELECT * FROM clientes LIMIT 10"
                    }
                },
                "required": ["sql"],
            },
        },
    )
    TOOL_REGISTRY["consultar_sheet"] = ToolDefinition(
        fn=consultar_sheet,
        permission=Permission.READ_EXTERNAL_DB,
        schema={
            "name": "consultar_sheet",
            "description": "Consulta datos de una hoja de Google Sheets del cliente (símil de SQL SELECT). "
                           "Usa 'hoja' con el nombre exacto de la pestaña detectada. "
                           "'filtros' filtra por columnas {'Columna': 'valor'} (coincidencia sin importar mayúsculas).",
            "parameters": {
                "type": "object",
                "properties": {
                    "hoja": {
                        "type": "string",
                        "description": "Nombre exacto de la pestaña a consultar. Ej: 'Clientes', 'Ventas'",
                    },
                    "filtros": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Filtros columna → valor. Coincidencia case-insensitive. Ej: {'Ciudad': 'Bogotá'}",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Máximo de filas a retornar (default 1000, techo 5000)",
                    },
                },
                "required": ["hoja"],
            },
        },
    )
    TOOL_REGISTRY["consultar_alegra"] = ToolDefinition(
        fn=consultar_alegra,
        permission=Permission.READ_EXTERNAL_DB,
        schema={
            "name": "consultar_alegra",
            "description": "Consulta información de Alegra (contabilidad) del cliente. "
                           "Ejemplos: facturas del mes, clientes con saldo, productos, "
                           "reporte de ventas, movimientos bancarios.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {
                        "type": "string",
                        "description": "Pregunta en lenguaje natural. "
                                       "Ej: 'facturas de este mes', 'clientes con saldo pendiente'",
                    },
                },
                "required": ["consulta"],
            },
        },
    )
    TOOL_REGISTRY["generar_informe_contable"] = ToolDefinition(
        fn=generar_informe_contable,
        permission=Permission.GENERATE_REPORT,
        schema={
            "name": "generar_informe_contable",
            "description": "Genera un PDF con informe contable personalizado del cliente. "
                           "Ej: balance general, estado de resultados, flujo de caja.",
            "parameters": {
                "type": "object",
                "properties": {
                    "secciones": {
                        "type": "array",
                        "description": "Lista de secciones del informe. Cada sección tiene: "
                                       "title (str), headers (list[str]), rows (list[list]), "
                                       "summary (str opcional).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "headers": {"type": "array", "items": {"type": "string"}},
                                "rows": {"type": "array", "items": {"type": "array"}},
                                "summary": {"type": "string"},
                            },
                            "required": ["title", "headers", "rows"],
                        },
                    },
                    "periodo": {
                        "type": "string",
                        "description": "Período del informe. Ej: 'Septiembre 2026'",
                    },
                    "titulo": {
                        "type": "string",
                        "description": "Título opcional del informe. Default: 'Informe Contable'",
                    },
                },
                "required": ["secciones", "periodo"],
            },
        },
    )


_register_all_tools()
