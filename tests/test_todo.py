"""Each shopping list as a Home Assistant to-do list."""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.nextcloud_shopping_list.api import ApiRefused
from custom_components.nextcloud_shopping_list.const import CONF_HIDDEN_LISTS
from custom_components.nextcloud_shopping_list.models import ShoppingListInfo

from .common import FakeServer, make_entry, make_item

ENTITY = "todo.weekly_shop"


@pytest.fixture
def server():
    fake = FakeServer()
    fake.items = {
        4: [
            make_item(7, "Milk", "2 pints", shop_area_id=38, added_via="Home Assistant"),
            make_item(8, "Bread", "1", shop_area_id=39),
            make_item(9, "Eggs", "12", shop_area_id=38, checked=True, checked_by_name="Sam"),
        ]
    }
    with fake.patches():
        yield fake


@pytest.fixture
async def entry(hass: HomeAssistant, server: FakeServer):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def get_items(hass: HomeAssistant, entity_id: str = ENTITY) -> list[dict]:
    result = await hass.services.async_call(
        "todo",
        "get_items",
        {"status": ["needs_action", "completed"]},
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    return result[entity_id]["items"]


async def test_items_render_as_layout_a(hass: HomeAssistant, entry) -> None:
    items = await get_items(hass)

    assert [(i["summary"], i.get("description"), i["status"]) for i in items] == [
        ("2 pints Milk", "Dairy · Home Assistant", "needs_action"),
        ("1 Bread", "Bakery · Adam", "needs_action"),
        ("12 Eggs", "Dairy · ticked by Sam", "completed"),
    ]
    assert hass.states.get(ENTITY).state == "2"


async def test_add_sends_text(hass: HomeAssistant, entry, server: FakeServer) -> None:
    await hass.services.async_call("todo", "add_item", {"item": "two pints of oat milk"}, target={"entity_id": ENTITY}, blocking=True)
    assert ("add_text", 4, "two pints of oat milk") in server.calls


async def test_tick_sends_check(hass: HomeAssistant, entry, server: FakeServer) -> None:
    await hass.services.async_call(
        "todo", "update_item", {"item": "2 pints Milk", "status": "completed"}, target={"entity_id": ENTITY}, blocking=True
    )
    assert server.calls == [("check", 4, 7, True)]


async def test_edit_sends_text(hass: HomeAssistant, entry, server: FakeServer) -> None:
    await hass.services.async_call(
        "todo", "update_item", {"item": "7", "rename": "3 pints Milk"}, target={"entity_id": ENTITY}, blocking=True
    )
    assert server.calls == [("update_text", 4, 7, "3 pints Milk")]


async def test_remove_completed_uses_clear_checked(hass: HomeAssistant, entry, server: FakeServer) -> None:
    await hass.services.async_call("todo", "remove_completed_items", {}, target={"entity_id": ENTITY}, blocking=True)
    assert server.calls == [("clear_checked", 4)]


async def test_delete_one_deletes_it(hass: HomeAssistant, entry, server: FakeServer) -> None:
    await hass.services.async_call("todo", "remove_item", {"item": "1 Bread"}, target={"entity_id": ENTITY}, blocking=True)
    assert server.calls == [("delete", 4, 8)]


async def test_move_reorders_open_items(hass: HomeAssistant, entry, server: FakeServer, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    # No previous_uid moves it to the top
    await client.send_json_auto_id({"type": "todo/item/move", "entity_id": ENTITY, "uid": "8"})
    response = await client.receive_json()

    assert response["success"]
    assert server.calls == [("reorder", 4, [8, 7])]


async def test_a_refused_change_shows_the_servers_message(hass: HomeAssistant, entry, server: FakeServer) -> None:
    async def refuse(_api, *args):
        raise ApiRefused("No permission")

    with patch("custom_components.nextcloud_shopping_list.api.ShoppingListApi.async_check", refuse), pytest.raises(
        HomeAssistantError, match="No permission"
    ):
        await hass.services.async_call(
            "todo", "update_item", {"item": "2 pints Milk", "status": "completed"}, target={"entity_id": ENTITY}, blocking=True
        )


async def test_new_list_adds_entity(hass: HomeAssistant, entry, server: FakeServer) -> None:
    server.lists.append(ShoppingListInfo(5, "Party"))
    server.items[5] = [make_item(11, "Crisps", list_id=5)]
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("todo.party").state == "1"


async def test_deleted_list_removes_entity(hass: HomeAssistant, entry, server: FakeServer, entity_registry: er.EntityRegistry) -> None:
    server.lists = []
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY) is None
    assert entity_registry.async_get(ENTITY) is None


async def test_hidden_list_entity_is_removed_on_setup(hass: HomeAssistant, server: FakeServer, entity_registry: er.EntityRegistry) -> None:
    server.lists = [ShoppingListInfo(4, "Weekly shop"), ShoppingListInfo(5, "Party")]
    entry = make_entry(hass, {CONF_HIDDEN_LISTS: [5]})
    # Left from before the list was hidden, or deleted while Home Assistant was down
    entity_registry.async_get_or_create(
        "todo", "nextcloud_shopping_list", "adam@cloud.example.com_5", config_entry=entry, suggested_object_id="party"
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get("todo.party") is None
    assert entity_registry.async_get(ENTITY) is not None


async def test_renamed_list_renames_entity(hass: HomeAssistant, entry, server: FakeServer) -> None:
    server.lists = [ShoppingListInfo(4, "Big shop")]
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY).attributes["friendly_name"] == "Big shop"
