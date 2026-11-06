"""WebSocket API for the dashboard card: the caller's topics, channels and subscriptions."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import SIGNAL_CONFIG_ENTRY_CHANGED, ConfigEntry, ConfigEntryChange
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .channels import Channel, all_channels
from .const import DOMAIN, KIND_MOBILE_APP, MOBILE_APP_DOMAIN, SIGNAL_UPDATED
from .delivery import effective_subscription
from .store import SubscriptionStore

WS_CONFIG = f"{DOMAIN}/config"
WS_SUBSCRIBE = f"{DOMAIN}/subscribe"

_COMPUTER_OS = ("macos", "mac os", "windows", "linux")


def channel_icon(channel: Channel) -> str:
    """A Material Design icon for the channel button."""
    if channel.kind == KIND_MOBILE_APP:
        os_name = (channel.os_name or "").lower()
        return "mdi:laptop" if os_name.startswith(_COMPUTER_OS) else "mdi:cellphone"
    target = channel.target.lower()
    if "telegram" in target:
        return "mdi:send"
    if "mail" in target or "smtp" in target:
        return "mdi:email-outline"
    return "mdi:message-text-outline"


def _store(hass: HomeAssistant) -> SubscriptionStore | None:
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        store: SubscriptionStore = entry.runtime_data
        return store
    return None


def user_view(hass: HomeAssistant, store: SubscriptionStore, user_id: str) -> dict[str, Any]:
    """Everything the card shows for one user."""
    mine = [c for c in all_channels(hass, store) if c.user_id == user_id]
    subscriptions = {}
    for topic in store.topics:
        sub = effective_subscription(store, user_id, topic)
        subscriptions[topic["id"]] = {"mode": sub["mode"], "channels": list(sub["channels"])}
    return {
        "topics": [{"id": t["id"], "name": t["name"], "icon": t["icon"]} for t in store.topics],
        "channels": [{"id": c.id, "name": c.name, "kind": c.kind, "icon": channel_icon(c)} for c in mine],
        "subscriptions": subscriptions,
    }


@websocket_api.websocket_command({vol.Required("type"): WS_CONFIG})
@callback
def ws_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """One-off read of the caller's view."""
    store = _store(hass)
    if store is None:
        connection.send_error(msg["id"], "not_loaded", "Notify Subscriptions is not set up")
        return
    connection.send_result(msg["id"], user_view(hass, store, connection.user.id))


@websocket_api.websocket_command({vol.Required("type"): WS_SUBSCRIBE})
@callback
def ws_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Send the caller's view now and again after every relevant change."""
    if _store(hass) is None:
        connection.send_error(msg["id"], "not_loaded", "Notify Subscriptions is not set up")
        return
    user_id = connection.user.id
    msg_id = msg["id"]

    @callback
    def push() -> None:
        store = _store(hass)
        if store is not None:
            connection.send_message(websocket_api.event_message(msg_id, user_view(hass, store, user_id)))

    @callback
    def on_device_change(event: Event[dr.EventDeviceRegistryUpdatedData]) -> None:
        push()

    @callback
    def on_entry_change(change: ConfigEntryChange, entry: ConfigEntry) -> None:
        if entry.domain == MOBILE_APP_DOMAIN:
            push()

    unsubs = [
        async_dispatcher_connect(hass, SIGNAL_UPDATED, push),
        async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, on_entry_change),
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, on_device_change),
    ]

    @callback
    def unsubscribe() -> None:
        for unsub in unsubs:
            unsub()

    connection.subscriptions[msg_id] = unsubscribe
    connection.send_result(msg_id)
    push()


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the card's commands."""
    websocket_api.async_register_command(hass, ws_config)
    websocket_api.async_register_command(hass, ws_subscribe)
