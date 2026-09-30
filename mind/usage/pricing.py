"""
Precios de modelos LLM para estimar el costo en USD del consumo de tokens.

Los precios están expresados en USD por 1 millón de tokens y corresponden a
tarifas públicas de referencia (OpenAI / OpenRouter). El objetivo es estimar
el consumo para el modelo de licenciamiento de Mind, no facturar con precisión
contable: si un modelo no está en la tabla se usa un precio genérico.
"""
from __future__ import annotations

# (input_usd_por_1M, output_usd_por_1M)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1-mini": (1.10, 4.40),
    "o1": (15.00, 60.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    # Anthropic
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-7-sonnet": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-opus": (15.00, 75.00),
    # Google
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    # Otros
    "deepseek-chat": (0.27, 1.10),
    "llama-3.3-70b": (0.12, 0.30),
    "mistral-large": (2.00, 6.00),
    "grok-2": (2.00, 10.00),
}

# Precio genérico cuando el modelo no se reconoce (conservador).
DEFAULT_PRICING: tuple[float, float] = (1.00, 3.00)

# Claves ordenadas de mayor a menor longitud para que "gpt-4.1-mini" gane
# antes que "gpt-4.1" en el matching por prefijo.
_PRICING_KEYS: tuple[str, ...] = tuple(
    sorted(MODEL_PRICING.keys(), key=len, reverse=True)
)


def normalize_model(model: str | None) -> str:
    """Normaliza el nombre del modelo: minúsculas y sin prefijo de proveedor."""
    name = (model or "").strip().lower()
    if "/" in name:
        name = name.split("/", 1)[1]
    return name


def get_pricing(model: str | None) -> tuple[float, float]:
    """Retorna (precio_input, precio_output) por 1M de tokens."""
    name = normalize_model(model)
    if name in MODEL_PRICING:
        return MODEL_PRICING[name]
    for key in _PRICING_KEYS:
        if name.startswith(key):
            return MODEL_PRICING[key]
    return DEFAULT_PRICING


def compute_cost_usd(
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float:
    """Calcula el costo estimado en USD de una interacción."""
    input_price, output_price = get_pricing(model)
    prompt = max(0, int(prompt_tokens or 0))
    completion = max(0, int(completion_tokens or 0))
    cost = (prompt / 1_000_000) * input_price + (completion / 1_000_000) * output_price
    return round(cost, 6)
