"""WebSocket API used by the dashboard card."""

from homeassistant.core import Context, HomeAssistant

from custom_components.notify_subscriptions.const import DOMAIN

from .conftest import set_topic


async def test_config_shows_only_the_callers_channels(
    hass: HomeAssistant, add_phone, setup_integration, hass_ws_client, hass_admin_user
) -> None:
    me = hass_admin_user.id
    phone = add_phone(me, "iPhone (Владислав)")
    mac = add_phone(me, "Macbook_Pro_Vlad")
    hass.config_entries.async_update_entry(mac.entry, data={**mac.entry.data, "os_name": "macOS"})
    add_phone("olha", "iPhone (2)")
    await set_topic(hass, "air_raid", default_mode="all", icon="mdi:bell-ring")
    await set_topic(hass, "power_change")
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": f"{DOMAIN}/config"})
    msg = await client.receive_json()

    assert msg["success"]
    result = msg["result"]
    assert [t["id"] for t in result["topics"]] == ["air_raid", "power_change"]
    assert result["topics"][0]["icon"] == "mdi:bell-ring"
    channels = {c["id"]: c for c in result["channels"]}
    assert set(channels) == {phone.channel_id, mac.channel_id}
    assert channels[phone.channel_id]["icon"] == "mdi:cellphone"
    assert channels[mac.channel_id]["icon"] == "mdi:laptop"
    # never changed -> the topic default is shown
    assert result["subscriptions"]["air_raid"] == {"mode": "all", "channels": []}
    assert result["subscriptions"]["power_change"] == {"mode": "off", "channels": []}


async def test_subscribe_pushes_updates(
    hass: HomeAssistant, add_phone, setup_integration, hass_ws_client, hass_admin_user
) -> None:
    me = hass_admin_user.id
    phone = add_phone(me, "iPhone (Владислав)")
    await set_topic(hass, "air_raid", default_mode="all")
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"]["subscriptions"]["air_raid"]["mode"] == "all"

    await hass.services.async_call(
        DOMAIN,
        "set_subscription",
        {"topic": "air_raid", "mode": "toggle", "channel": phone.channel_id},
        blocking=True,
        context=Context(user_id=me),
    )
    update = await client.receive_json()

    assert update["event"]["subscriptions"]["air_raid"] == {"mode": "off", "channels": []}


async def test_subscribe_pushes_new_device(
    hass: HomeAssistant, add_phone, setup_integration, hass_ws_client, hass_admin_user
) -> None:
    await set_topic(hass, "air_raid")
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]
    assert (await client.receive_json())["event"]["channels"] == []

    add_phone(hass_admin_user.id, "New phone")
    update = await client.receive_json()

    assert [c["name"] for c in update["event"]["channels"]] == ["New phone"]


async def test_not_loaded_is_an_error(hass: HomeAssistant, hass_ws_client) -> None:
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, DOMAIN, {})
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_loaded"
