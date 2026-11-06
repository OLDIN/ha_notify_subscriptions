"""notify_subscriptions.send: who receives what."""

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.notify_subscriptions.const import DOMAIN

from .conftest import set_topic


async def _send(hass: HomeAssistant, topic: str, **data):
    return await hass.services.async_call(
        DOMAIN,
        "send",
        {"topic": topic, "title": "⚠️ Power", "message": "The power is off", **data},
        blocking=True,
        return_response=True,
    )


@pytest.fixture
async def home(hass: HomeAssistant, add_phone, setup_integration):
    """Vlad: iPhone + Mac, Olha: iPhone."""
    return {
        "vlad_phone": add_phone("vlad", "iPhone (Владислав)", "mobile_app_iphone_vladislav"),
        "vlad_mac": add_phone("vlad", "Macbook_Pro_Vlad", "mobile_app_macbook_pro_vlad"),
        "olha_phone": add_phone("olha", "iPhone (2)", "mobile_app_iphone_2"),
    }


async def _subscribe(hass: HomeAssistant, user, topic: str, mode: str, channel: str | None = None) -> None:
    data = {"topic": topic, "mode": mode}
    if channel:
        data["channel"] = channel
    await hass.services.async_call(DOMAIN, "set_subscription", data, blocking=True, context=Context(user_id=user))


async def test_default_all_sends_to_every_device(hass: HomeAssistant, home) -> None:
    await set_topic(hass, "air_raid", default_mode="all")

    response = await _send(hass, "air_raid")

    for phone in home.values():
        assert len(phone.calls) == 1
        assert phone.calls[0].data == {"title": "⚠️ Power", "message": "The power is off"}
    assert len(response["sent"]) == 3
    assert response["failed"] == []


async def test_default_off_sends_nothing(hass: HomeAssistant, home) -> None:
    await set_topic(hass, "power_warning")

    response = await _send(hass, "power_warning")

    assert all(not p.calls for p in home.values())
    assert response == {"sent": [], "failed": []}


async def test_picked_devices_only(hass: HomeAssistant, home) -> None:
    await set_topic(hass, "power_change", default_mode="all")
    # Vlad turns the Mac off: from "all" the toggle leaves only the iPhone
    await _subscribe(hass, "vlad", "power_change", "toggle", home["vlad_mac"].channel_id)
    await _subscribe(hass, "olha", "power_change", "off")

    await _send(hass, "power_change")

    assert len(home["vlad_phone"].calls) == 1
    assert home["vlad_mac"].calls == []
    assert home["olha_phone"].calls == []


async def test_topic_data_is_merged_with_call_data(hass: HomeAssistant, home) -> None:
    await set_topic(hass, "air_raid", default_mode="all", data={"push": {"sound": "alarm"}, "tag": "x"})

    await _send(hass, "air_raid", data={"tag": "ukraine_alarm"})

    assert home["olha_phone"].calls[0].data["data"] == {"push": {"sound": "alarm"}, "tag": "ukraine_alarm"}


async def test_one_failing_channel_does_not_block_others(hass: HomeAssistant, add_phone, setup_integration) -> None:
    good = add_phone("vlad", "iPhone (Владислав)", "mobile_app_iphone_vladislav")
    add_phone("vlad", "Phone without push")  # no notify service registered
    await set_topic(hass, "air_raid", default_mode="all")

    response = await _send(hass, "air_raid")

    assert len(good.calls) == 1
    assert [s["name"] for s in response["sent"]] == ["iPhone (Владислав)"]
    assert response["failed"][0]["name"] == "Phone without push"
    assert "not found" in response["failed"][0]["error"]


async def test_manual_channels_service_and_entity(hass: HomeAssistant, setup_integration, hass_admin_user) -> None:
    telegram = async_mock_service(hass, "notify", "telegram_andrii")
    send_message = async_mock_service(hass, "notify", "send_message")
    hass.states.async_set("notify.smtp_maria", "unknown")
    user = hass_admin_user.id
    for cid, target in (("telegram", "notify.telegram_andrii"), ("mail", "notify.smtp_maria")):
        await hass.services.async_call(
            DOMAIN, "set_channel", {"id": cid, "user_id": user, "name": cid, "target": target}, blocking=True
        )
    await set_topic(hass, "washer_done", default_mode="all")

    await _send(hass, "washer_done", data={"ignored_by_entities": True})

    assert telegram[0].data == {
        "title": "⚠️ Power",
        "message": "The power is off",
        "data": {"ignored_by_entities": True},
    }
    assert send_message[0].data == {"entity_id": "notify.smtp_maria", "title": "⚠️ Power", "message": "The power is off"}


async def test_unknown_topic_is_an_error(hass: HomeAssistant, home) -> None:
    with pytest.raises(ServiceValidationError, match="Unknown topic"):
        await _send(hass, "nope")
