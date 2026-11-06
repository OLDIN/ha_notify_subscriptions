"""Constants for the Notify Subscriptions integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "notify_subscriptions"

STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1

# Subscription modes
MODE_OFF: Final = "off"
MODE_ALL: Final = "all"
MODE_PICKED: Final = "picked"
MODES: Final = (MODE_OFF, MODE_ALL, MODE_PICKED)
# Extra pseudo-mode accepted by set_subscription: flip one channel
MODE_TOGGLE: Final = "toggle"

# Channel kinds
KIND_MOBILE_APP: Final = "mobile_app"
KIND_MANUAL: Final = "manual"

MOBILE_APP_DOMAIN: Final = "mobile_app"
NOTIFY_DOMAIN: Final = "notify"

# Dispatcher signal fired after topics, channels or subscriptions change
SIGNAL_UPDATED: Final = f"{DOMAIN}_updated"

# Services
SERVICE_SEND: Final = "send"
SERVICE_SET_SUBSCRIPTION: Final = "set_subscription"
SERVICE_TEST: Final = "test"
SERVICE_SET_TOPIC: Final = "set_topic"
SERVICE_REMOVE_TOPIC: Final = "remove_topic"
SERVICE_SET_CHANNEL: Final = "set_channel"
SERVICE_REMOVE_CHANNEL: Final = "remove_channel"
SERVICE_IMPORT_LEGACY: Final = "import_legacy"

# Service fields
ATTR_TOPIC: Final = "topic"
ATTR_TITLE: Final = "title"
ATTR_MESSAGE: Final = "message"
ATTR_DATA: Final = "data"
ATTR_MODE: Final = "mode"
ATTR_CHANNEL: Final = "channel"
ATTR_ID: Final = "id"
ATTR_NAME: Final = "name"
ATTR_ICON: Final = "icon"
ATTR_DEFAULT_MODE: Final = "default_mode"
ATTR_USER_ID: Final = "user_id"
ATTR_TARGET: Final = "target"
ATTR_ENTITY_ID: Final = "entity_id"

# Legacy token prefixes (input_text based setup): u:<user_id>, d:<device_tracker object id>
LEGACY_USER_PREFIX: Final = "u:"
LEGACY_DEVICE_PREFIX: Final = "d:"

TEST_MESSAGES: Final = {
    "uk": ("🔔 Тест сповіщення", "Так приходитиме: «{topic}»."),
    "en": ("🔔 Test notification", "This is how “{topic}” will arrive."),
}
