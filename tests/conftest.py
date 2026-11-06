"""Shared test fixtures."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.notify_subscriptions.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let HA load custom_components/notify_subscriptions in tests."""
    yield


@dataclass
class Phone:
    """A fake Companion app registration."""

    entry: MockConfigEntry
    device: dr.DeviceEntry
    channel_id: str
    calls: list[ServiceCall]


@pytest.fixture
def add_phone(hass: HomeAssistant) -> Callable[..., Phone]:
    """Register a mobile_app config entry, its device, tracker and notify service (no real app needed)."""

    def _add(user_id: str, device_name: str, service: str | None = None, tracker: str | None = None) -> Phone:
        device_id = uuid.uuid4().hex
        entry = MockConfigEntry(
            domain="mobile_app",
            title=device_name,
            data={
                "user_id": user_id,
                "device_name": device_name,
                "device_id": device_id,
                "app_id": "io.robbie.HomeAssistant",
                "os_name": "iOS",
            },
        )
        entry.add_to_hass(hass)
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={("mobile_app", device_id)}, name=device_name
        )
        if tracker:
            er.async_get(hass).async_get_or_create(
                "device_tracker",
                "mobile_app",
                f"{device_id}_tracker",
                suggested_object_id=tracker,
                config_entry=entry,
                device_id=device.id,
            )
        calls = async_mock_service(hass, "notify", service) if service else []
        return Phone(entry=entry, device=device, channel_id=f"mobile_app:{entry.entry_id}", calls=calls)

    return _add


@pytest.fixture
async def setup_integration(hass: HomeAssistant) -> MockConfigEntry:
    """Set up Notify Subscriptions with an empty store."""
    entry = MockConfigEntry(domain=DOMAIN, title="Notify Subscriptions", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def set_topic(hass: HomeAssistant, topic_id: str, default_mode: str = "off", **extra: Any) -> None:
    """Create a topic as the system (admin services allow calls without a user)."""
    await hass.services.async_call(
        DOMAIN,
        "set_topic",
        {"id": topic_id, "name": topic_id.replace("_", " ").title(), "default_mode": default_mode, **extra},
        blocking=True,
    )
