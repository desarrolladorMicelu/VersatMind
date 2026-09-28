"""
Conector MCP a Alegra (contabilidad).

Usa el SDK `mcp` para conectarse al MCP server de Alegra
vía Streamable HTTP con autenticación Basic.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Grupos de solo lectura para un dueño de negocio
READONLY_GROUPS = [
    "contacts", "items", "invoices", "banks", "income-payments",
    "reports", "taxes", "sellers", "currencies", "resolutions",
    "config", "ledger",
]

# Tools de escritura a filtrar (cualquier tool cuyo nombre contenga estos patrones)
WRITE_PATTERNS = ("__create_", "__update_", "__delete_", "__void", "__close",
                  "__add_", "__email", "__upload_", "__import_", "__apply")


class AlegraError(Exception):
    """Error de conexión/consulta a Alegra."""


def _basic_token(email: str, token: str) -> str:
    """Construye el token Basic: Base64(email:token)."""
    raw = f"{email}:{token}"
    return base64.b64encode(raw.encode()).decode()


def _is_readonly(tool_name: str) -> bool:
    """True si la herramienta MCP es solo lectura."""
    name_lower = tool_name.lower()
    for p in WRITE_PATTERNS:
        if p in name_lower:
            return False
    return True


async def discover_tools(conf: dict) -> list[dict]:
    """
    Conecta al MCP server de Alegra y descubre las tools disponibles.
    Retorna solo las tools de solo lectura.
    """
    from mcp import Client

    email = (conf or {}).get("email", "")
    token = (conf or {}).get("token", "")
    if not email or not token:
        raise AlegraError("Faltan email o token de Alegra.")

    auth = _basic_token(email, token)
    groups = conf.get("groups") or READONLY_GROUPS
    headers = {
        "Authorization": f"Basic {auth}",
        "mcp-groups": ",".join(groups),
    }

    try:
        async with Client("https://mcp.alegra.com/mcp", headers=headers) as client:
            result = await asyncio.wait_for(client.list_tools(), timeout=15)
            if not result or not result.tools:
                raise AlegraError("No se encontraron tools en el servidor MCP.")
            tools = [
                {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                for t in result.tools
                if _is_readonly(t.name)
            ]
            if not tools:
                raise AlegraError(
                    "No se encontraron tools de solo lectura. "
                    "Verifica que el token tenga permisos de consulta."
                )
            return tools
    except asyncio.TimeoutError:
        raise AlegraError("Timeout conectando al MCP server de Alegra (15 s).")
    except Exception as exc:
        raise AlegraError(f"Error conectando a Alegra MCP: {type(exc).__name__}: {exc}") from exc


async def call_tool(conf: dict, tool_name: str, arguments: dict) -> Any:
    """
    Llama una herramienta del MCP server de Alegra.
    """
    from mcp import Client

    email = (conf or {}).get("email", "")
    token = (conf or {}).get("token", "")
    auth = _basic_token(email, token)
    groups = conf.get("groups") or READONLY_GROUPS
    headers = {
        "Authorization": f"Basic {auth}",
        "mcp-groups": ",".join(groups),
    }

    try:
        async with Client("https://mcp.alegra.com/mcp", headers=headers) as client:
            result = await asyncio.wait_for(
                client.call_tool(tool_name, arguments), timeout=25
            )
            return result.structured_content if hasattr(result, "structured_content") else result.content
    except asyncio.TimeoutError:
        raise AlegraError("Timeout llamando tool de Alegra (25 s).")
    except Exception as exc:
        raise AlegraError(f"Error llamando {tool_name}: {type(exc).__name__}: {exc}") from exc


async def generate_description(conf: dict) -> str:
    """
    Conecta a Alegra, descubre las tools y genera una descripción
    del contexto disponible para el agente.
    """
    tools = await discover_tools(conf)

    lines = ["## Alegra (Contabilidad)", ""]
    lines.append(f"Tienes disponible la contabilidad de Alegra con {len(tools)} herramientas de consulta.")
    lines.append("")

    groups: dict[str, list[dict]] = {}
    for t in tools:
        prefix = t["name"].split("__")[0] if "__" in t["name"] else "general"
        groups.setdefault(prefix, []).append(t)

    for gname, gtools in sorted(groups.items()):
        lines.append(f"### {gname}")
        for t in gtools:
            desc = (t.get("description") or "")[:120]
            lines.append(f"- `{t['name']}`: {desc}")
        lines.append("")

    return "\n".join(lines)


async def test_connection(conf: dict) -> list[str]:
    """
    Prueba la conexión a Alegra y retorna los nombres de las tools disponibles.
    """
    tools = await discover_tools(conf)
    return [t["name"] for t in tools]