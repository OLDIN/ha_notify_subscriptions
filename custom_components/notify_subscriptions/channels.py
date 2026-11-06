"""Channels: where a notification can be delivered for a given user.

* Companion app devices (``mobile_app``) are discovered automatically. The owner is the
  ``user_id`` stored in the mobile_app config entry, the target is the
  ``notify.mobile_app_<slug of the registered device name>`` service.
* Manual channels are added by an admin and bound to a user. Their target is either a
  notify service (``notify.telegram_family``) or a notify entity (``notify.smtp_maria``).
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import slugify

from .const import KIND_MANUAL, KIND_MOBILE_APP, MOBILE_APP_DOMAIN
from .store import SubscriptionStore

# Keys of a mobile_app config entry (homeassistant.components.mobile_app.const)
_MA_USER_ID = "user_id"
_MA_DEVICE_ID = "device_id"
_MA_DEVICE_NAME = "device_name"
_MA_OS_NAME = "os_name"


@dataclass(frozen=True)
class Channel:
    """A delivery target owned by one Home Assistant user."""

    id: str
    user_id: str
    name: str
    kind: str
    # mobile_app: notify service name without the domain ("mobile_app_iphone").
    # manual: a notify entity id ("notify.smtp_maria") or a notify service, with or
    # without the domain ("notify.telegram_family" / "telegram_family").
    target: str
    os_name: str | None = None


def mobile_app_channel_id(entry_id: str) -> str:
    """Stable channel id of a mobile_app config entry."""
    return f"{KIND_MOBILE_APP}:{entry_id}"


def mobile_app_channels(hass: HomeAssistant) -> list[Channel]:
    """Channels for every enabled Companion app registration that has an owner."""
    registry = dr.async_get(hass)
    result: list[Channel] = []
    for entry in hass.config_entries.async_entries(MOBILE_APP_DOMAIN):
        if entry.disabled_by is not None:
            continue
        user_id = entry.data.get(_MA_USER_ID)
        device_name = entry.data.get(_MA_DEVICE_NAME)
        if not user_id or not device_name:
            continue
        name = device_name
        device_id = entry.data.get(_MA_DEVICE_ID)
        if device_id:
            device = registry.async_get_device(identifiers={(MOBILE_APP_DOMAIN, device_id)})
            if device is not None:
                name = device.name_by_user or device.name or device_name
        result.append(
            Channel(
                id=mobile_app_channel_id(entry.entry_id),
                user_id=user_id,
                name=name,
                kind=KIND_MOBILE_APP,
                target=f"mobile_app_{slugify(device_name)}",
                os_name=entry.data.get(_MA_OS_NAME),
            )
        )
    return result


def manual_channels(store: SubscriptionStore) -> list[Channel]:
    """Channels added by an admin."""
    result: list[Channel] = []
    for data in store.manual_channels:
        result.append(
            Channel(id=data["id"], user_id=data["user_id"], name=data["name"], kind=KIND_MANUAL, target=data["target"])
        )
    return result


def all_channels(hass: HomeAssistant, store: SubscriptionStore) -> list[Channel]:
    """Every known channel, mobile_app first."""
    return [*mobile_app_channels(hass), *manual_channels(store)]


def channels_by_user(channels: list[Channel]) -> dict[str, list[Channel]]:
    """Group channels by owner, keeping their order."""
    grouped: dict[str, list[Channel]] = {}
    for channel in channels:
        grouped.setdefault(channel.user_id, []).append(channel)
    return grouped
