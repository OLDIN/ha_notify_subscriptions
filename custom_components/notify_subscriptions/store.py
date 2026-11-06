"""Persistent storage of topics, manual channels and subscriptions."""

from __future__ import annotations

from typing import Any, TypedDict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import MODE_OFF, MODE_PICKED, SIGNAL_UPDATED, STORAGE_KEY, STORAGE_VERSION


class TopicData(TypedDict):
    """A notification topic, e.g. ``air_raid``."""

    id: str
    name: str
    icon: str | None
    default_mode: str
    data: dict[str, Any]


class ManualChannelData(TypedDict):
    """A channel added by an admin, bound to one user (Telegram, e-mail, ...)."""

    id: str
    user_id: str
    name: str
    target: str


class SubscriptionData(TypedDict):
    """One user's subscription to one topic."""

    mode: str
    channels: list[str]


class StoreData(TypedDict):
    """Everything the integration persists."""

    topics: dict[str, TopicData]
    channels: dict[str, ManualChannelData]
    subscriptions: dict[str, dict[str, SubscriptionData]]


def _empty() -> StoreData:
    return {"topics": {}, "channels": {}, "subscriptions": {}}


class SubscriptionStore:
    """Wraps ``helpers.storage.Store``; every change is saved at once and announced."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store[StoreData] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: StoreData = _empty()

    async def async_load(self) -> None:
        """Load the stored data (an empty structure on first run)."""
        loaded = await self._store.async_load()
        data = _empty()
        if loaded:
            data["topics"] = dict(loaded.get("topics", {}))
            data["channels"] = dict(loaded.get("channels", {}))
            data["subscriptions"] = dict(loaded.get("subscriptions", {}))
        self._data = data

    async def _async_save(self) -> None:
        await self._store.async_save(self._data)
        self._notify()

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self._hass, SIGNAL_UPDATED)

    # ------------------------------------------------------------ topics

    @property
    def topics(self) -> list[TopicData]:
        """Topics in creation order."""
        return list(self._data["topics"].values())

    def get_topic(self, topic_id: str) -> TopicData | None:
        """Return a topic by id."""
        return self._data["topics"].get(topic_id)

    async def async_set_topic(self, topic: TopicData) -> None:
        """Create or replace a topic (its position is kept on update)."""
        self._data["topics"][topic["id"]] = topic
        await self._async_save()

    async def async_remove_topic(self, topic_id: str) -> bool:
        """Remove a topic and every subscription to it."""
        if self._data["topics"].pop(topic_id, None) is None:
            return False
        for user_subs in self._data["subscriptions"].values():
            user_subs.pop(topic_id, None)
        await self._async_save()
        return True

    # ------------------------------------------------------------ manual channels

    @property
    def manual_channels(self) -> list[ManualChannelData]:
        """Channels added by an admin."""
        return list(self._data["channels"].values())

    async def async_set_channel(self, channel: ManualChannelData) -> None:
        """Create or replace a manual channel."""
        self._data["channels"][channel["id"]] = channel
        await self._async_save()

    async def async_remove_channel(self, channel_id: str) -> bool:
        """Remove a manual channel and drop it from picked lists."""
        if self._data["channels"].pop(channel_id, None) is None:
            return False
        for user_subs in self._data["subscriptions"].values():
            for sub in user_subs.values():
                if channel_id in sub["channels"]:
                    sub["channels"] = [c for c in sub["channels"] if c != channel_id]
                    # A picked list that became empty means the user no longer gets this topic
                    if not sub["channels"] and sub["mode"] == MODE_PICKED:
                        sub["mode"] = MODE_OFF
        await self._async_save()
        return True

    # ------------------------------------------------------------ subscriptions

    def get_subscription(self, user_id: str, topic_id: str) -> SubscriptionData | None:
        """Return the stored subscription; ``None`` means the topic default applies."""
        return self._data["subscriptions"].get(user_id, {}).get(topic_id)

    async def async_set_subscriptions(self, changes: dict[tuple[str, str], SubscriptionData]) -> None:
        """Store several (user_id, topic_id) subscriptions with one save."""
        for (user_id, topic_id), sub in changes.items():
            self._data["subscriptions"].setdefault(user_id, {})[topic_id] = {
                "mode": sub["mode"],
                "channels": list(sub["channels"]),
            }
        await self._async_save()
