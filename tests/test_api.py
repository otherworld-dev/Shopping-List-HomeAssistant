"""The client for the Shopping List app's API."""

import asyncio
import base64

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nextcloud_shopping_list.api import (
    ApiAuthError,
    ApiConnectionError,
    ApiRefused,
    ShoppingListApi,
)
from custom_components.nextcloud_shopping_list.models import ShoppingListInfo

from .conftest import BASE, CAPABILITIES, FEATURES, SERVER, item_json, ocs


def make_api(hass: HomeAssistant, via: str | None = "Home Assistant") -> ShoppingListApi:
    return ShoppingListApi(async_get_clientsession(hass), SERVER, "adam", "app-pass", via)


def last_headers(aioclient_mock: AiohttpClientMocker) -> dict:
    return dict(aioclient_mock.mock_calls[-1][3] or {})


async def test_requests_carry_ocs_headers_and_auth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/lists", json=ocs([{"id": 4, "title": "Weekly shop", "userId": "adam"}]))

    lists = await make_api(hass).async_lists()

    assert lists == [ShoppingListInfo(id=4, title="Weekly shop")]
    headers = last_headers(aioclient_mock)
    assert headers["OCS-APIRequest"] == "true"
    assert headers["Accept"] == "application/json"
    assert headers["Authorization"] == "Basic " + base64.b64encode(b"adam:app-pass").decode()


async def test_reads_carry_no_via_header(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/lists", json=ocs([]))
    await make_api(hass).async_lists()
    assert "X-Shopping-List-Via" not in last_headers(aioclient_mock)


async def test_writes_carry_the_via_header(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.put(f"{BASE}/lists/4/items/7/check", json=ocs(item_json(checked=True)))
    await make_api(hass).async_check(4, 7, True)
    assert last_headers(aioclient_mock)["X-Shopping-List-Via"] == "Home Assistant"
    assert aioclient_mock.mock_calls[-1][2] == {"checked": True}


async def test_no_via_label_sends_no_header(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.put(f"{BASE}/lists/4/items/7/check", json=ocs(item_json(checked=True)))
    await make_api(hass, via=None).async_check(4, 7, True)
    assert "X-Shopping-List-Via" not in last_headers(aioclient_mock)


async def test_add_text_posts_text_and_parses_item(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{BASE}/lists/4/items", status=201, json=ocs(item_json() | {"outcome": "created"}, 201))

    item = await make_api(hass).async_add_text(4, "two pints of milk")

    assert aioclient_mock.mock_calls[-1][2] == {"text": "two pints of milk"}
    assert item.name == "Milk"
    assert item.quantity == "2 pints"
    assert item.added_via == "Home Assistant"
    assert item.shop_area_id == 38


async def test_update_text_sends_text(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.put(f"{BASE}/lists/4/items/7", json=ocs(item_json(quantity="3 pints")))
    await make_api(hass).async_update_text(4, 7, "3 pints Milk")
    assert aioclient_mock.mock_calls[-1][2] == {"text": "3 pints Milk"}


async def test_update_amount_sends_amount_text(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.put(f"{BASE}/lists/4/items/7", json=ocs(item_json(quantity="3 pints")))
    item = await make_api(hass).async_update_amount(4, 7, "three pints")
    assert aioclient_mock.mock_calls[-1][2] == {"amountText": "three pints"}
    assert item.quantity == "3 pints"


async def test_delete_and_clear_and_reorder(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.delete(f"{BASE}/lists/4/items/7", status=204)
    aioclient_mock.delete(f"{BASE}/lists/4/items/checked", json=ocs(None))
    aioclient_mock.post(f"{BASE}/lists/4/items/reorder", json=ocs(None))
    api = make_api(hass)

    await api.async_delete(4, 7)
    await api.async_clear_checked(4)
    await api.async_reorder(4, [9, 7, 8])

    assert aioclient_mock.mock_calls[-1][2] == {"sortedIds": [9, 7, 8]}
    assert aioclient_mock.call_count == 3


async def test_401_raises_auth_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/lists", status=401, json={"ocs": {"meta": {"statuscode": 997}, "data": []}})
    with pytest.raises(ApiAuthError):
        await make_api(hass).async_lists()


async def test_400_raises_refused_with_the_servers_message(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.put(f"{BASE}/lists/4/items/7", status=400, json=ocs({"message": "That is not an amount"}, 400))
    with pytest.raises(ApiRefused, match="That is not an amount"):
        await make_api(hass).async_update_amount(4, 7, "lots")


async def test_timeout_raises_connection_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/lists", exc=asyncio.TimeoutError())
    with pytest.raises(ApiConnectionError):
        await make_api(hass).async_lists()


async def test_features_reads_capabilities(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(
        CAPABILITIES,
        json=ocs({"capabilities": {"shopping_list": {"version": "1.13.0", "features": FEATURES}}}),
    )
    assert await make_api(hass).async_features() == ("1.13.0", FEATURES)


async def test_features_without_the_app(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(CAPABILITIES, json=ocs({"capabilities": {"core": {}}}))
    assert await make_api(hass).async_features() == (None, [])


async def test_items_and_areas_parse(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/lists/4/items", json=ocs([item_json(), item_json(id=8, name="Bread", shopAreaId=None)]))
    aioclient_mock.get(f"{BASE}/lists/4/areas", json=ocs([{"id": 38, "listId": 4, "name": "Dairy", "sortOrder": 1, "color": None, "keywords": []}]))
    api = make_api(hass)

    items = await api.async_items(4)
    areas = await api.async_areas(4)

    assert [i.name for i in items] == ["Milk", "Bread"]
    assert items[1].shop_area_id is None
    assert areas[0].name == "Dairy"
    assert areas[0].sort_order == 1
