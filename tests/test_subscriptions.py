"""set_subscription, test, admin services, import and persistence."""

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.setup import async_setup_component

from custom_components.notify_subscriptions.const import DOMAIN
from custom_components.notify_subscriptions.services import next_subscription

from .conftest import set_topic

ALL = {"mode": "all", "channels": []}
OFF = {"mode": "off", "channels": []}


def test_next_subscription_modes() -> None:
    mine = ["a", "b", "c"]
    assert next_subscription(OFF, "all", mine, None) == ALL
    assert next_subscription(ALL, "off", mine, None) == OFF
    assert next_subscription(OFF, "picked", mine, None) == {"mode": "picked", "channels": mine}
    # toggling from "all" removes that device, the rest stay picked
    assert next_subscription(ALL, "toggle", mine, "b") == {"mode": "picked", "channels": ["a", "c"]}
    # toggling from "off" picks only that device
    assert next_subscription(OFF, "toggle", mine, "c") == {"mode": "picked", "channels": ["c"]}
    # order follows the user's devices, not the click order
    assert next_subscription({"mode": "picked", "channels": ["c"]}, "toggle", mine, "a") == {
        "mode": "picked",
        "channels": ["a", "c"],
    }
    # removing the last picked device turns the topic off
    assert next_subscription({"mode": "picked", "channels": ["a"]}, "toggle", mine, "a") == OFF


def test_toggle_needs_own_channel() -> None:
    with pytest.raises(ServiceValidationError):
        next_subscription(ALL, "toggle", ["a"], "someone_elses")
    with pytest.raises(ServiceValidationError):
        next_subscription(ALL, "toggle", ["a"], None)


async def test_set_subscription_needs_a_user(hass: HomeAssistant, setup_integration) -> None:
    await set_topic(hass, "air_raid")
    with pytest.raises(ServiceValidationError, match="user who calls"):
        await hass.services.async_call(DOMAIN, "set_subscription", {"topic": "air_raid", "mode": "all"}, blocking=True)


async def test_set_subscription_changes_only_the_caller(hass: HomeAssistant, add_phone, setup_integration) -> None:
    vlad = add_phone("vlad", "iPhone (Владислав)", "mobile_app_iphone_vladislav")
    olha = add_phone("olha", "iPhone (2)", "mobile_app_iphone_2")
    await set_topic(hass, "air_raid", default_mode="all")

    await hass.services.async_call(
        DOMAIN,
        "set_subscription",
        {"topic": "air_raid", "mode": "off"},
        blocking=True,
        context=Context(user_id="vlad"),
    )
    await hass.services.async_call(DOMAIN, "send", {"topic": "air_raid", "message": "x"}, blocking=True)

    assert vlad.calls == []
    assert len(olha.calls) == 1


async def test_cannot_toggle_someone_elses_device(hass: HomeAssistant, add_phone, setup_integration) -> None:
    add_phone("vlad", "iPhone (Владислав)")
    olha = add_phone("olha", "iPhone (2)")
    await set_topic(hass, "air_raid", default_mode="all")

    with pytest.raises(ServiceValidationError, match="own channels"):
        await hass.services.async_call(
            DOMAIN,
            "set_subscription",
            {"topic": "air_raid", "mode": "toggle", "channel": olha.channel_id},
            blocking=True,
            context=Context(user_id="vlad"),
        )


async def test_test_service_only_notifies_the_caller(hass: HomeAssistant, add_phone, setup_integration) -> None:
    hass.config.language = "uk"
    vlad = add_phone("vlad", "iPhone (Владислав)", "mobile_app_iphone_vladislav")
    olha = add_phone("olha", "iPhone (2)", "mobile_app_iphone_2")
    await hass.services.async_call(
        DOMAIN, "set_topic", {"id": "air_raid", "name": "Повітряна тривога", "default_mode": "all"}, blocking=True
    )

    await hass.services.async_call(
        DOMAIN, "test", {"topic": "air_raid"}, blocking=True, context=Context(user_id="vlad")
    )

    assert vlad.calls[0].data == {"title": "🔔 Тест сповіщення", "message": "Так приходитиме: «Повітряна тривога»."}
    assert olha.calls == []


async def test_admin_services_reject_regular_users(hass: HomeAssistant, setup_integration, hass_read_only_user) -> None:
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "set_topic",
            {"id": "air_raid", "name": "Air raid"},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )


async def test_remove_topic_drops_its_subscriptions(hass: HomeAssistant, add_phone, setup_integration) -> None:
    add_phone("vlad", "iPhone (Владислав)")
    await set_topic(hass, "air_raid")
    await hass.services.async_call(
        DOMAIN, "set_subscription", {"topic": "air_raid", "mode": "all"}, blocking=True, context=Context(user_id="vlad")
    )
    store = setup_integration.runtime_data

    await hass.services.async_call(DOMAIN, "remove_topic", {"id": "air_raid"}, blocking=True)

    assert store.get_topic("air_raid") is None
    assert store.get_subscription("vlad", "air_raid") is None
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "remove_topic", {"id": "air_raid"}, blocking=True)


async def test_import_legacy_input_text(hass: HomeAssistant, add_phone, setup_integration) -> None:
    vlad_phone = add_phone("vlad", "iPhone (Владислав)", tracker="iphone_vladislav")
    add_phone("vlad", "Macbook_Pro_Vlad", tracker="macbook_pro_vlad")
    add_phone("olha", "iPhone (2)", tracker="iphone")
    add_phone("guest", "Guest phone")
    await set_topic(hass, "power_change", default_mode="all")
    hass.states.async_set("input_text.notify_subs_power_change", "u:olha, d:iphone_vladislav,d:unknown_tracker")

    response = await hass.services.async_call(
        DOMAIN,
        "import_legacy",
        {"topic": "power_change", "entity_id": "input_text.notify_subs_power_change"},
        blocking=True,
        return_response=True,
    )

    store = setup_integration.runtime_data
    assert store.get_subscription("olha", "power_change") == ALL
    assert store.get_subscription("vlad", "power_change") == {"mode": "picked", "channels": [vlad_phone.channel_id]}
    # not mentioned -> off, so the "all" default does not subscribe them
    assert store.get_subscription("guest", "power_change") == OFF
    assert response["skipped"] == ["d:unknown_tracker"]


async def test_data_survives_restart(hass: HomeAssistant, add_phone, setup_integration) -> None:
    add_phone("vlad", "iPhone (Владислав)")
    await set_topic(hass, "air_raid", default_mode="all", icon="mdi:bell-ring")
    await hass.services.async_call(
        DOMAIN, "set_subscription", {"topic": "air_raid", "mode": "off"}, blocking=True, context=Context(user_id="vlad")
    )

    assert await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()

    store = setup_integration.runtime_data
    assert store.get_topic("air_raid")["icon"] == "mdi:bell-ring"
    assert store.get_subscription("vlad", "air_raid") == OFF


async def test_services_before_setup_report_clear_error(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError, match="not set up"):
        await hass.services.async_call(DOMAIN, "send", {"topic": "x", "message": "y"}, blocking=True)


async def test_removing_last_picked_channel_turns_topic_off(hass: HomeAssistant, setup_integration) -> None:
    user = await hass.auth.async_create_user("Andrii")
    await hass.services.async_call(
        DOMAIN,
        "set_channel",
        {"id": "telegram", "user_id": user.id, "name": "Telegram", "target": "notify.telegram_andrii"},
        blocking=True,
    )
    await set_topic(hass, "washer_done")
    await hass.services.async_call(
        DOMAIN,
        "set_subscription",
        {"topic": "washer_done", "mode": "toggle", "channel": "telegram"},
        blocking=True,
        context=Context(user_id=user.id),
    )
    store = setup_integration.runtime_data
    assert store.get_subscription(user.id, "washer_done") == {"mode": "picked", "channels": ["telegram"]}

    await hass.services.async_call(DOMAIN, "remove_channel", {"id": "telegram"}, blocking=True)

    assert store.get_subscription(user.id, "washer_done") == OFF
    with pytest.raises(ServiceValidationError, match="Unknown channel"):
        await hass.services.async_call(DOMAIN, "remove_channel", {"id": "telegram"}, blocking=True)


async def test_channel_for_unknown_user_is_rejected(hass: HomeAssistant, setup_integration) -> None:
    with pytest.raises(ServiceValidationError, match="Unknown user"):
        await hass.services.async_call(
            DOMAIN,
            "set_channel",
            {"id": "telegram", "user_id": "nobody", "name": "Telegram", "target": "notify.telegram_x"},
            blocking=True,
        )
