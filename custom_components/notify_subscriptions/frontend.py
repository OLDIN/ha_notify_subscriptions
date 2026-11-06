"""Serve the dashboard card and register it as a Lovelace resource."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STATIC_URL = f"/{DOMAIN}_static"
CARD_FILE = "notify-subscriptions-card.js"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve frontend/ and add the card to the dashboard resources (storage mode only)."""
    if "http" not in hass.config.components:
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), cache_headers=False)]
    )
    version = (await async_get_integration(hass, DOMAIN)).version
    base = f"{STATIC_URL}/{CARD_FILE}"
    url = f"{base}?v={version}"

    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        # YAML-mode dashboards: the user adds the resource by hand (see README)
        _LOGGER.debug("Lovelace resources are not editable; add %s manually", url)
        return
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    current = [r for r in resources.async_items() if str(r.get("url", "")).split("?")[0] == base]
    if any(r.get("url") == url for r in current):
        return
    # Drop the resource of an older version so browsers load the new card
    for item in current:
        await resources.async_delete_item(item["id"])
    await resources.async_create_item({"res_type": "module", "url": url})
