"""Notify Subscriptions: every user picks which notifications they get and where."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .services import async_register_services
from .store import SubscriptionStore

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type NotifySubscriptionsConfigEntry = ConfigEntry[SubscriptionStore]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services; they report a clear error until the entry is loaded."""
    async_register_services(hass)
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
