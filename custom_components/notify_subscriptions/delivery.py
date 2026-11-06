"""Who gets a topic, and sending to them."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant

from .channels import Channel, all_channels, channels_by_user
from .const import KIND_MOBILE_APP, MODE_ALL, MODE_OFF, MODE_PICKED, NOTIFY_DOMAIN
from .store import SubscriptionData, SubscriptionStore, TopicData

_LOGGER = logging.getLogger(__name__)


def effective_subscription(store: SubscriptionStore, user_id: str, topic: TopicData) -> SubscriptionData:
    """The stored subscription, or the topic default for users who never changed it."""
    stored = store.get_subscription(user_id, topic["id"])
    if stored is not None:
        return stored
    return {"mode": topic["default_mode"], "channels": []}


def channels_for_subscription(sub: SubscriptionData, user_channels: list[Channel]) -> list[Channel]:
    """The user's channels this subscription delivers to."""
    if sub["mode"] == MODE_ALL:
        return list(user_channels)
    if sub["mode"] == MODE_PICKED:
        return [c for c in user_channels if c.id in sub["channels"]]
    return []


def resolve_recipients(
    hass: HomeAssistant, store: SubscriptionStore, topic: TopicData, only_user: str | None = None
) -> list[Channel]:
    """Every channel that should receive ``topic`` (optionally for one user only)."""
    result: list[Channel] = []
    for user_id, user_channels in channels_by_user(all_channels(hass, store)).items():
        if only_user is not None and user_id != only_user:
            continue
        sub = effective_subscription(store, user_id, topic)
        if sub["mode"] == MODE_OFF:
            continue
        result.extend(channels_for_subscription(sub, user_channels))
    return result


@dataclass
class DeliveryResult:
    """Outcome of one send."""

    sent: list[Channel] = field(default_factory=list)
    failed: list[tuple[Channel, str]] = field(default_factory=list)

    def as_response(self) -> dict[str, Any]:
        """Service response data."""
        return {
            "sent": [{"channel": c.id, "name": c.name, "user_id": c.user_id} for c in self.sent],
            "failed": [{"channel": c.id, "name": c.name, "user_id": c.user_id, "error": e} for c, e in self.failed],
        }


def _service_name(hass: HomeAssistant, channel: Channel) -> str | None:
    """The notify service to call, or ``None`` when the target is a notify entity."""
    target = channel.target
    if channel.kind == KIND_MOBILE_APP:
        return target
    prefix = f"{NOTIFY_DOMAIN}."
    if target.startswith(prefix):
        if hass.states.get(target) is not None:
            return None
        return target[len(prefix) :]
    return target


async def _deliver_one(
    hass: HomeAssistant, channel: Channel, title: str | None, message: str, data: dict[str, Any]
) -> None:
    service = _service_name(hass, channel)
    if service is None:
        # Notify entities take only a message and a title
        entity_payload: dict[str, Any] = {"entity_id": channel.target, "message": message}
        if title:
            entity_payload["title"] = title
        await hass.services.async_call(NOTIFY_DOMAIN, "send_message", entity_payload, blocking=True)
        return
    if not hass.services.has_service(NOTIFY_DOMAIN, service):
        raise LookupError(f"{NOTIFY_DOMAIN}.{service} not found")
    payload: dict[str, Any] = {"message": message}
    if title:
        payload["title"] = title
    if data:
        payload["data"] = data
    await hass.services.async_call(NOTIFY_DOMAIN, service, payload, blocking=True)


async def async_deliver(
    hass: HomeAssistant,
    channels: list[Channel],
    title: str | None,
    message: str,
    data: dict[str, Any] | None = None,
) -> DeliveryResult:
    """Send to every channel in parallel; one failing channel never blocks the others."""
    result = DeliveryResult()
    payload_data = data or {}
    outcomes = await asyncio.gather(
        *(_deliver_one(hass, c, title, message, payload_data) for c in channels), return_exceptions=True
    )
    for channel, outcome in zip(channels, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            _LOGGER.warning("Could not notify %s (%s): %s", channel.name, channel.id, outcome)
            result.failed.append((channel, str(outcome) or type(outcome).__name__))
        else:
            result.sent.append(channel)
    return result
