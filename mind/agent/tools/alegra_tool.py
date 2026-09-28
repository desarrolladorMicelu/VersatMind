"""
Herramienta `consultar_alegra`: consulta datos de Alegra (contabilidad)
del cliente vía MCP.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


async def consultar_alegra(consulta: str) -> dict:
    """
    Consulta información de Alegra del tenant activo.
    - `consulta`: descripción en lenguaje natural de lo que se necesita
      (ej: "facturas de este mes", "clientes con saldo pendiente").
    """
    from mind.tenants.context import get_tenant
    from mind.data.alegra.alegra_mcp import (
        discover_tools,
        call_tool,
        AlegraError,
    )

    tenant = get_tenant()
    conf = getattr(tenant, "external_alegra", None)
    if not conf or not conf.get("token"):
        return {
            "error": True,
            "mensaje": "No hay conexión con Alegra configurada.",
        }

    try:
        tools = await discover_tools(conf)
    except AlegraError as exc:
        return {"error": True, "mensaje": str(exc)}

    # Construir un prompt para que el LLM decida qué tool(s) llamar
    tool_descriptions = "\n".join(
        f"- {t['name']}: {t.get('description', '')[:150]}"
        for t in tools
    )

    # Usar un LLM local para traducir la consulta a tool call
    from mind.config import settings
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=30,
    )

    decision_prompt = (
        "Eres un asistente que traduce preguntas de negocios en llamadas a "
        "herramientas MCP de Alegra. Dada la siguiente pregunta del usuario "
        "y la lista de herramientas disponibles, responde ÚNICAMENTE con un "
        "JSON con la tool a llamar y sus argumentos.\n\n"
        "Pregunta: {consulta}\n\n"
        "Herramientas disponibles:\n{tool_descriptions}\n\n"
        "Reglas:\n"
        "- Responde solo con un JSON: {{\"tool\": \"nombre_exacto\", "
        "\"arguments\": {{...}}}}\n"
        "- Si no hay una herramienta adecuada, responde "
        "{{\"tool\": null, \"reason\": \"explicación\"}}\n"
        "- Usa los nombres exactos de las herramientas."
    ).format(consulta=consulta, tool_descriptions=tool_descriptions)

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": decision_prompt}],
            response_format={"type": "json_object"},
        )
        decision = json.loads(response.choices[0].message.content)
    except Exception as exc:
        return {"error": True, "mensaje": f"Error al decidir qué consultar: {exc}"}

    tool_name = decision.get("tool")
    if not tool_name:
        return {
            "error": True,
            "mensaje": decision.get("reason", "No supe qué tool usar para esa consulta."),
        }

    arguments = decision.get("arguments", {})
    try:
        result = await call_tool(conf, tool_name, arguments)
        return {"error": False, "data": result, "tool": tool_name}
    except AlegraError as exc:
        return {"error": True, "mensaje": str(exc)}
    except Exception as exc:
        logger.warning("Error en consultar_alegra tenant=%s: %s", tenant.slug, exc)
        return {"error": True, "mensaje": str(exc)}