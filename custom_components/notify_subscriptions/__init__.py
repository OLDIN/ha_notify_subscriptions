"""Notify Subscriptions: every user picks which notifications they get and where."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .frontend import async_register_frontend
from .services import async_register_services
from .store import SubscriptionStore
from .websocket import async_register_websocket

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type NotifySubscriptionsConfigEntry = ConfigEntry[SubscriptionStore]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services, the card's WebSocket API and the card itself."""
    async_register_services(hass)
    async_register_websocket(hass)
    await async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NotifySubscriptionsConfigEntry) -> bool:
    """Load the stored topics and subscriptions."""
    store = SubscriptionStore(hass)
    await store.async_load()
    entry.runtime_data = store
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NotifySubscriptionsConfigEntry) -> bool:
    """Nothing to tear down: the data stays in .storage."""
    return True
