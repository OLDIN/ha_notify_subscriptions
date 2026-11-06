"""The card is served and registered as a dashboard resource."""

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.notify_subscriptions.const import DOMAIN
from custom_components.notify_subscriptions.frontend import CARD_FILE, STATIC_URL

CARD = Path(__file__).parent.parent / "custom_components" / DOMAIN / "frontend" / CARD_FILE


async def test_card_resource_is_registered_once_and_updated(hass: HomeAssistant, hass_client) -> None:
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data["lovelace"].resources
    await resources.async_load()
    resources.loaded = True
    # a resource of an older version must be replaced
    await resources.async_create_item({"res_type": "module", "url": f"{STATIC_URL}/{CARD_FILE}?v=0.0.1"})

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    urls = [r["url"] for r in resources.async_items() if CARD_FILE in r["url"]]
    assert len(urls) == 1
    assert urls[0].startswith(f"{STATIC_URL}/{CARD_FILE}?v=")
    assert not urls[0].endswith("0.0.1")

    client = await hass_client()
    response = await client.get(f"{STATIC_URL}/{CARD_FILE}")
    assert response.status == 200
    assert "notify-subscriptions-card" in await response.text()


def test_card_file_exists() -> None:
    assert CARD.is_file()
