"""Discovery of Companion app channels."""

from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.notify_subscriptions.channels import channels_by_user, mobile_app_channels


async def test_mobile_app_channels_have_owner_and_service(hass: HomeAssistant, add_phone) -> None:
    vlad_phone = add_phone("vlad", "iPhone (Владислав)")
    vlad_mac = add_phone("vlad", "Macbook_Pro_Vlad")
    olha_phone = add_phone("olha", "iPhone (2)")

    channels = {c.id: c for c in mobile_app_channels(hass)}

    assert channels[vlad_phone.channel_id].target == "mobile_app_iphone_vladislav"
    assert channels[vlad_mac.channel_id].target == "mobile_app_macbook_pro_vlad"
    assert channels[olha_phone.channel_id].target == "mobile_app_iphone_2"
    grouped = channels_by_user(list(channels.values()))
    assert {c.id for c in grouped["vlad"]} == {vlad_phone.channel_id, vlad_mac.channel_id}
    assert [c.id for c in grouped["olha"]] == [olha_phone.channel_id]


async def test_user_renamed_device_name_is_shown(hass: HomeAssistant, add_phone) -> None:
    mac = add_phone("vlad", "Macbook_Pro_Vlad")
    dr.async_get(hass).async_update_device(mac.device.id, name_by_user="MacBook Pro")

    (channel,) = mobile_app_channels(hass)

    assert channel.name == "MacBook Pro"
    # the notify service keeps the registered name
    assert channel.target == "mobile_app_macbook_pro_vlad"


async def test_registration_without_user_or_disabled_is_skipped(hass: HomeAssistant, add_phone) -> None:
    add_phone("", "Shared tablet")
    disabled = add_phone("vlad", "Old phone")
    await hass.config_entries.async_set_disabled_by(disabled.entry.entry_id, disabled_by=ConfigEntryDisabler.USER)

    assert mobile_app_channels(hass) == []
