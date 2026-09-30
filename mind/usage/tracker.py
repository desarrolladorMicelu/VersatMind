"""
Registro de consumo de tokens y evaluación del umbral de alerta.

`record_usage` persiste una fila por interacción y, si el usuario supera el
umbral configurado para su tenant, crea una alerta y notifica al administrador
(Telegram y/o email). Nunca lanza excepción hacia el flujo del agente.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func as sqlfunc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.usage.pricing import compute_cost_usd

logger = logging.getLogger(__name__)

PERIOD_MONTH = "month"
PERIOD_TOTAL = "total"


@dataclass
class EffectiveUsageSettings:
    threshold_usd: float
    period: str
    auto_pause: bool
    notify_telegram: bool
    notify_email: bool
    admin_email: str | None


def period_bounds(period: str, now: datetime | None = None) -> tuple[datetime | None, str, str]:
    """
    Retorna (inicio_periodo, period_key, etiqueta).
    - "month": primer día del mes calendario actual (UTC).
    - "total": sin límite inferior (acumulado histórico).
    """
    now = now or datetime.now(timezone.utc)
    if period == PERIOD_TOTAL:
        return None, "total", "Acumulado histórico"
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    key = f"{now.year:04d}-{now.month:02d}"
    return start, key, f"Mes {key}"


async def get_usage_settings(session: AsyncSession, tenant_id: int) -> EffectiveUsageSettings:
    """Lee la configuración de consumo del tenant o retorna los valores por defecto."""
    from mind.config import settings
    from mind.db.models import UsageSettings

    row = (await session.execute(
        select(UsageSettings).where(UsageSettings.tenant_id == tenant_id).limit(1)
    )).scalar_one_or_none()

    if row is None:
        return EffectiveUsageSettings(
            threshold_usd=settings.USAGE_DEFAULT_THRESHOLD_USD,
            period=settings.USAGE_DEFAULT_PERIOD,
            auto_pause=False,
            notify_telegram=True,
            notify_email=False,
            admin_email=None,
        )
    return EffectiveUsageSettings(
        threshold_usd=float(row.threshold_usd),
        period=row.period or PERIOD_MONTH,
        auto_pause=bool(row.auto_pause),
        notify_telegram=bool(row.notify_telegram),
        notify_email=bool(row.notify_email),
        admin_email=row.admin_email,
    )


async def _evaluate_and_maybe_alert(
    session: AsyncSession,
    tenant_id: int,
    chat_id: int,
    username: str | None,
    user_id: int | None,
):
    """Evalúa el umbral y, si se supera, crea la alerta. Retorna notificación o None."""
    from mind.db.models import Tenant, TokenUsage, UsageAlert, User
    from mind.usage.notifier import UsageAlertNotification

    conf = await get_usage_settings(session, tenant_id)
    if conf.threshold_usd <= 0:
        return None

    start, period_key, period_label = period_bounds(conf.period)

    cost_stmt = select(
        sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0.0),
        sqlfunc.coalesce(sqlfunc.sum(TokenUsage.total_tokens), 0),
    ).where(TokenUsage.tenant_id == tenant_id, TokenUsage.chat_id == chat_id)
    if start is not None:
        cost_stmt = cost_stmt.where(TokenUsage.created_at >= start)
    total_cost, total_tokens = (await session.execute(cost_stmt)).one()
    total_cost = float(total_cost or 0.0)
    total_tokens = int(total_tokens or 0)

    if total_cost < conf.threshold_usd:
        return None

    existing = (await session.execute(
        select(UsageAlert.id).where(
            UsageAlert.tenant_id == tenant_id,
            UsageAlert.chat_id == chat_id,
            UsageAlert.period_key == period_key,
            UsageAlert.threshold_usd == conf.threshold_usd,
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        return None

    user = (await session.execute(
        select(User).where(User.chat_id == chat_id, User.tenant_id == tenant_id)
    )).scalar_one_or_none()

    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()

    display_username = (user.username if user and user.username else username)

    paused = False
    if conf.auto_pause and user is not None and not user.is_paused:
        user.is_paused = True
        user.paused_reason = f"Bolsa de tokens agotada (consumo ${total_cost:.2f} USD)"
        user.paused_at = datetime.now(timezone.utc)
        paused = True

    alert = UsageAlert(
        tenant_id=tenant_id,
        chat_id=chat_id,
        user_id=user.user_id if user else user_id,
        username=display_username,
        threshold_usd=conf.threshold_usd,
        total_cost_usd=round(total_cost, 4),
        total_tokens=total_tokens,
        period_key=period_key,
        status="active",
        notified=False,
    )
    session.add(alert)

    return UsageAlertNotification(
        tenant_id=tenant_id,
        tenant_name=tenant.name if tenant else f"Tenant {tenant_id}",
        bot_token=tenant.bot_token if tenant else None,
        admin_chat_id=tenant.admin_chat_id if tenant else None,
        chat_id=chat_id,
        username=display_username,
        user_id=user.user_id if user else user_id,
        threshold_usd=conf.threshold_usd,
        total_cost_usd=total_cost,
        total_tokens=total_tokens,
        period_label=period_label,
        paused=paused,
        notify_telegram=conf.notify_telegram,
        notify_email=conf.notify_email,
        admin_email=conf.admin_email,
    )


async def record_usage(
    *,
    tenant_id: int,
    chat_id: int | None,
    user_id: int | None,
    username: str | None,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    source: str = "chat",
) -> None:
    """
    Persiste el consumo de una interacción y dispara alertas si corresponde.
    Tolerante a fallos: cualquier error se registra en logs y no se propaga.
    """
    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return

    try:
        from mind.db.base import _session_factory
        from mind.db.models import TokenUsage
        from mind.usage.notifier import notify_usage_alert, notify_user_paused

        if _session_factory is None:
            return

        total_tokens = prompt_tokens + completion_tokens
        cost = compute_cost_usd(model, prompt_tokens, completion_tokens)

        notification = None
        async with _session_factory() as session:
            session.add(TokenUsage(
                tenant_id=tenant_id,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                model=model or "",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost,
                source=source,
            ))
            await session.flush()

            if chat_id is not None:
                notification = await _evaluate_and_maybe_alert(
                    session, tenant_id, chat_id, username, user_id
                )
            await session.commit()

        if notification is not None:
            await notify_usage_alert(notification)
            if notification.paused:
                await notify_user_paused(notification.bot_token, notification.chat_id)
    except Exception as exc:
        logger.warning(
            "No se pudo registrar consumo de tokens tenant=%s chat_id=%s: %s",
            tenant_id, chat_id, exc,
        )
