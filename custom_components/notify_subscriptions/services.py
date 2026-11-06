"""Service actions of the integration."""

from __future__ import annotations

import logging
from typing import cast

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_register_admin_service

from .channels import all_channels, channels_by_user, mobile_app_channel_id
from .const import (
    ATTR_CHANNEL,
    ATTR_DATA,
    ATTR_DEFAULT_MODE,
    ATTR_ENTITY_ID,
    ATTR_ICON,
    ATTR_ID,
    ATTR_MESSAGE,
    ATTR_MODE,
    ATTR_NAME,
    ATTR_TARGET,
    ATTR_TITLE,
    ATTR_TOPIC,
    ATTR_USER_ID,
    DOMAIN,
    LEGACY_DEVICE_PREFIX,
    LEGACY_USER_PREFIX,
    MOBILE_APP_DOMAIN,
    MODE_ALL,
    MODE_OFF,
    MODE_PICKED,
    MODE_TOGGLE,
    MODES,
    SERVICE_IMPORT_LEGACY,
    SERVICE_REMOVE_CHANNEL,
    SERVICE_REMOVE_TOPIC,
    SERVICE_SEND,
    SERVICE_SET_CHANNEL,
    SERVICE_SET_SUBSCRIPTION,
    SERVICE_SET_TOPIC,
    SERVICE_TEST,
    TEST_MESSAGES,
)
from .delivery import async_deliver, effective_subscription, resolve_recipients
from .store import SubscriptionData, SubscriptionStore, TopicData

_LOGGER = logging.getLogger(__name__)

_SLUG = vol.All(cv.string, vol.Match(r"^[a-z0-9_]+$", msg="use lowercase latin letters, digits and _"))

SEND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TOPIC): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_DATA): dict,
    }
)
SET_SUBSCRIPTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TOPIC): cv.string,
        vol.Required(ATTR_MODE): vol.In([*MODES, MODE_TOGGLE]),
        vol.Optional(ATTR_CHANNEL): cv.string,
    }
)
TEST_SCHEMA = vol.Schema({vol.Required(ATTR_TOPIC): cv.string})
SET_TOPIC_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ID): _SLUG,
        vol.Required(ATTR_NAME): cv.string,
        vol.Optional(ATTR_ICON): cv.icon,
        vol.Optional(ATTR_DEFAULT_MODE, default=MODE_OFF): vol.In([MODE_OFF, MODE_ALL]),
        vol.Optional(ATTR_DATA, default={}): dict,
    }
)
REMOVE_TOPIC_SCHEMA = vol.Schema({vol.Required(ATTR_ID): _SLUG})
SET_CHANNEL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ID): _SLUG,
        vol.Required(ATTR_USER_ID): cv.string,
        vol.Required(ATTR_NAME): cv.string,
        vol.Required(ATTR_TARGET): cv.string,
    }
)
REMOVE_CHANNEL_SCHEMA = vol.Schema({vol.Required(ATTR_ID): _SLUG})
IMPORT_LEGACY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TOPIC): cv.string,
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    }
)


def _get_store(hass: HomeAssistant) -> SubscriptionStore:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            store: SubscriptionStore = entry.runtime_data
            return store
    raise ServiceValidationError("Notify Subscriptions is not set up")


def _get_topic(store: SubscriptionStore, topic_id: str) -> TopicData:
    topic = store.get_topic(topic_id)
    if topic is None:
        raise ServiceValidationError(f"Unknown topic: {topic_id}")
    return topic


def _caller(call: ServiceCall) -> str:
    user_id = call.context.user_id
    if not user_id:
        raise ServiceValidationError("This action changes the subscriptions of the user who calls it")
    return user_id


def next_subscription(
    current: SubscriptionData, mode: str, my_channel_ids: list[str], channel: str | None
) -> SubscriptionData:
    """The subscription after a set_subscription call (pure, unit-tested)."""
    if mode == MODE_OFF:
        return {"mode": MODE_OFF, "channels": []}
    if mode == MODE_ALL:
        return {"mode": MODE_ALL, "channels": []}
    if mode == MODE_PICKED:
        # Start from every device; the user then turns off the ones they do not want
        return {"mode": MODE_PICKED, "channels": list(my_channel_ids)}
    # toggle one channel
    if channel is None or channel not in my_channel_ids:
        raise ServiceValidationError("Pick one of your own channels")
    if current["mode"] == MODE_ALL:
        base = list(my_channel_ids)
    elif current["mode"] == MODE_PICKED:
        base = [c for c in current["channels"] if c in my_channel_ids]
    else:
        base = []
    picked = [c for c in base if c != channel] if channel in base else [*base, channel]
    # keep the user's device order
    picked = [c for c in my_channel_ids if c in picked]
    if not picked:
        return {"mode": MODE_OFF, "channels": []}
    return {"mode": MODE_PICKED, "channels": picked}


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register every service of the integration (once, from async_setup)."""

    async def handle_send(call: ServiceCall) -> ServiceResponse:
        store = _get_store(hass)
        topic = _get_topic(store, call.data[ATTR_TOPIC])
        recipients = resolve_recipients(hass, store, topic)
        data = {**topic["data"], **call.data.get(ATTR_DATA, {})}
        result = await async_deliver(hass, recipients, call.data.get(ATTR_TITLE), call.data[ATTR_MESSAGE], data)
        if not recipients:
            _LOGGER.debug("Topic %s has no subscribers", topic["id"])
        return result.as_response()

    async def handle_set_subscription(call: ServiceCall) -> None:
        store = _get_store(hass)
        user_id = _caller(call)
        topic = _get_topic(store, call.data[ATTR_TOPIC])
        mine = [c.id for c in channels_by_user(all_channels(hass, store)).get(user_id, [])]
        current = effective_subscription(store, user_id, topic)
        new = next_subscription(current, call.data[ATTR_MODE], mine, call.data.get(ATTR_CHANNEL))
        await store.async_set_subscriptions({(user_id, topic["id"]): new})

    async def handle_test(call: ServiceCall) -> ServiceResponse:
        store = _get_store(hass)
        user_id = _caller(call)
        topic = _get_topic(store, call.data[ATTR_TOPIC])
        title, message = TEST_MESSAGES.get(hass.config.language, TEST_MESSAGES["en"])
        recipients = resolve_recipients(hass, store, topic, only_user=user_id)
        result = await async_deliver(hass, recipients, title, message.format(topic=topic["name"]), topic["data"])
        return result.as_response()

    async def handle_set_topic(call: ServiceCall) -> None:
        store = _get_store(hass)
        await store.async_set_topic(
            {
                "id": call.data[ATTR_ID],
                "name": call.data[ATTR_NAME],
                "icon": call.data.get(ATTR_ICON),
                "default_mode": call.data[ATTR_DEFAULT_MODE],
                "data": call.data[ATTR_DATA],
            }
        )

    async def handle_remove_topic(call: ServiceCall) -> None:
        if not await _get_store(hass).async_remove_topic(call.data[ATTR_ID]):
            raise ServiceValidationError(f"Unknown topic: {call.data[ATTR_ID]}")

    async def handle_set_channel(call: ServiceCall) -> None:
        store = _get_store(hass)
        if await hass.auth.async_get_user(call.data[ATTR_USER_ID]) is None:
            raise ServiceValidationError(f"Unknown user: {call.data[ATTR_USER_ID]}")
        await store.async_set_channel(
            {
                "id": call.data[ATTR_ID],
                "user_id": call.data[ATTR_USER_ID],
                "name": call.data[ATTR_NAME],
                "target": call.data[ATTR_TARGET],
            }
        )

    async def handle_remove_channel(call: ServiceCall) -> None:
        if not await _get_store(hass).async_remove_channel(call.data[ATTR_ID]):
            raise ServiceValidationError(f"Unknown channel: {call.data[ATTR_ID]}")

    async def handle_import_legacy(call: ServiceCall) -> ServiceResponse:
        store = _get_store(hass)
        topic = _get_topic(store, call.data[ATTR_TOPIC])
        state = hass.states.get(call.data[ATTR_ENTITY_ID])
        if state is None:
            raise ServiceValidationError(f"Entity not found: {call.data[ATTR_ENTITY_ID]}")
        changes, skipped = legacy_subscriptions(hass, store, topic["id"], state.state)
        await store.async_set_subscriptions(changes)
        imported = {user_id: dict(sub) for (user_id, _), sub in changes.items()}
        return cast(ServiceResponse, {"imported": imported, "skipped": skipped})

    hass.services.async_register(
        DOMAIN, SERVICE_SEND, handle_send, schema=SEND_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SUBSCRIPTION, handle_set_subscription, schema=SET_SUBSCRIPTION_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TEST, handle_test, schema=TEST_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    async_register_admin_service(hass, DOMAIN, SERVICE_SET_TOPIC, handle_set_topic, SET_TOPIC_SCHEMA)
    async_register_admin_service(hass, DOMAIN, SERVICE_REMOVE_TOPIC, handle_remove_topic, REMOVE_TOPIC_SCHEMA)
    async_register_admin_service(hass, DOMAIN, SERVICE_SET_CHANNEL, handle_set_channel, SET_CHANNEL_SCHEMA)
    async_register_admin_service(hass, DOMAIN, SERVICE_REMOVE_CHANNEL, handle_remove_channel, REMOVE_CHANNEL_SCHEMA)
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_IMPORT_LEGACY,
        handle_import_legacy,
        IMPORT_LEGACY_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _tracker_channel_id(hass: HomeAssistant, object_id: str) -> str | None:
    """Map ``device_tracker.<object_id>`` to the channel of its Companion app, if any."""
    entity = er.async_get(hass).async_get(f"device_tracker.{object_id}")
    if entity is None or entity.device_id is None:
        return None
    device = dr.async_get(hass).async_get(entity.device_id)
    if device is None:
        return None
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == MOBILE_APP_DOMAIN:
            return mobile_app_channel_id(entry.entry_id)
    return None


def legacy_subscriptions(
    hass: HomeAssistant, store: SubscriptionStore, topic_id: str, value: str
) -> tuple[dict[tuple[str, str], SubscriptionData], list[str]]:
    """Translate an ``input_text`` value like ``u:<user_id>,d:<tracker>`` into subscriptions.

    Every user who owns channels but is not mentioned is set to ``off``, so the topic default
    does not subscribe them behind their back.
    """
    by_user = channels_by_user(all_channels(hass, store))
    owner_of = {c.id: c.user_id for chans in by_user.values() for c in chans}
    everyone: set[str] = set(by_user)
    picked: dict[str, list[str]] = {}
    all_users: set[str] = set()
    skipped: list[str] = []
    for raw in value.split(","):
        token = raw.strip()
        if not token:
            continue
        if token.startswith(LEGACY_USER_PREFIX):
            all_users.add(token[len(LEGACY_USER_PREFIX) :])
        elif token.startswith(LEGACY_DEVICE_PREFIX):
            channel_id = _tracker_channel_id(hass, token[len(LEGACY_DEVICE_PREFIX) :])
            if channel_id is None or channel_id not in owner_of:
                skipped.append(token)
                continue
            picked.setdefault(owner_of[channel_id], []).append(channel_id)
        else:
            skipped.append(token)
    changes: dict[tuple[str, str], SubscriptionData] = {}
    for user_id in everyone | all_users | set(picked):
        if user_id in all_users:
            sub: SubscriptionData = {"mode": MODE_ALL, "channels": []}
        elif user_id in picked:
            sub = {"mode": MODE_PICKED, "channels": picked[user_id]}
        else:
            sub = {"mode": MODE_OFF, "channels": []}
        changes[(user_id, topic_id)] = sub
    return changes, skipped
