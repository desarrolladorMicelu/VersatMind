"""
Auto-reparación de webhooks de Telegram.

Revisa periódicamente que cada bot tenga su webhook apuntando a la URL pública
correcta y lo re-registra si falta o cambió. Así, aunque un despliegue o un
reinicio deje el webhook sin configurar, el bot se recupera solo sin que nadie
tenga que ponerlo a mano.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300


async def ensure_all_webhooks_once() -> int:
    """Verifica/repara el webhook de todos los bots activos. Devuelve cuántos OK."""
    from mind.tenants.resolver import get_all_cached
    from mind.telegram.bot import ensure_webhook, get_all_applications

    apps = get_all_applications()
    ok = 0
    for tenant in get_all_cached():
        if tenant.bot_token not in apps:
            continue
        try:
            if await ensure_webhook(tenant.bot_token, tenant.webhook_url):
                ok += 1
        except Exception as exc:
            logger.debug("webhook guard falló tenant=%s: %s", tenant.slug, exc)
    return ok


async def webhook_guard_loop(interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
    """Loop infinito que repara webhooks cada `interval_seconds`."""
    while True:
        try:
            await ensure_all_webhooks_once()
        except Exception as exc:
            logger.warning("webhook guard error: %s", exc)
        await asyncio.sleep(interval_seconds)
