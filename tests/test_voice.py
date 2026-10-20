"""Check off, change and remove by voice, through Home Assistant's own assistant."""

import pytest
from homeassistant.components.conversation import async_converse
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.nextcloud_shopping_list.const import CONF_HIDDEN_LISTS
from custom_components.nextcloud_shopping_list.models import ShoppingListInfo
from custom_components.nextcloud_shopping_list.voice import sentences_for, spoken_name

from .common import FakeServer, make_entry, make_item

ENTITY = "todo.weekly_shop"


@pytest.fixture
def server():
    fake = FakeServer()
    fake.items = {4: [make_item(7, "Milk", "2 pints"), make_item(8, "Bananas", "6")]}
    with fake.patches():
        yield fake


@pytest.fixture
async def entry(hass: HomeAssistant, server: FakeServer):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def say(hass: HomeAssistant, text: str) -> str:
    result = await async_converse(hass, text, None, Context(), language="en", agent_id="conversation.home_assistant")
    return result.response.speech["plain"]["speech"]


def test_spoken_name_drops_symbols() -> None:
    assert spoken_name("Tesco (big shop)") == "tesco big shop"
    assert spoken_name("Mum's | list") == "mums list"
    assert spoken_name("  Weekly   Shop ") == "weekly shop"


def test_sentences_name_the_lists() -> None:
    sentences = sentences_for("check", ["weekly shop", "shopping list"])
    assert all("(weekly shop|shopping list)" in s for s in sentences)
    assert all("{item}" in s for s in sentences)


async def test_check_off_by_name(hass: HomeAssistant, entry, server: FakeServer) -> None:
    assert await say(hass, "check off milk on weekly shop") == "Checked off Milk."
    assert server.calls == [("check", 4, 7, True)]


async def test_tick_off_with_the_and_list(hass: HomeAssistant, entry, server: FakeServer) -> None:
    assert await say(hass, "tick off the bananas on the weekly shop list") == "Checked off Bananas."


async def test_change_amount_sentence(hass: HomeAssistant, entry, server: FakeServer) -> None:
    await say(hass, "change milk to three pints on weekly shop")
    assert server.calls == [("update_amount", 4, 7, "three pints")]


async def test_remove_sentence(hass: HomeAssistant, entry, server: FakeServer) -> None:
    assert await say(hass, "remove milk from weekly shop") == "Removed Milk."
    assert server.calls == [("delete", 4, 7)]


async def test_alias_is_spoken(hass: HomeAssistant, entry, server: FakeServer, entity_registry: er.EntityRegistry) -> None:
    entity_registry.async_update_entity(ENTITY, aliases=["shopping list"])
    await hass.async_block_till_done()

    assert await say(hass, "check off milk on shopping list") == "Checked off Milk."


async def test_other_todo_lists_fall_through(hass: HomeAssistant, entry, server: FakeServer) -> None:
    speech = await say(hass, "check off milk on groceries")
    assert server.calls == []
    assert not speech.startswith(("Checked off", "I couldn't find milk on"))


async def test_renamed_list_matches_new_name_only(hass: HomeAssistant, entry, server: FakeServer) -> None:
    server.lists = [ShoppingListInfo(4, "Big shop")]
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    await say(hass, "check off milk on weekly shop")
    assert server.calls == []
    assert await say(hass, "check off milk on big shop") == "Checked off Milk."


async def test_titles_with_symbols_register(hass: HomeAssistant, server: FakeServer) -> None:
    server.lists = [ShoppingListInfo(4, "Tesco (big shop)")]
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await say(hass, "tick off milk on tesco big shop") == "Checked off Milk."


async def test_two_entries_both_register(hass: HomeAssistant, server: FakeServer) -> None:
    server.lists = [ShoppingListInfo(4, "Weekly shop"), ShoppingListInfo(5, "Party")]
    server.items[5] = [make_item(9, "Crisps", list_id=5)]
    first = make_entry(hass, {CONF_HIDDEN_LISTS: [5]})
    second = make_entry(hass, {CONF_HIDDEN_LISTS: [4]}, login="sam")
    # Setting the integration up loads every entry it has
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.LOADED

    assert await say(hass, "check off milk on weekly shop") == "Checked off Milk."
    assert await say(hass, "check off crisps on party") == "Checked off Crisps."
    assert server.calls == [("check", 4, 7, True), ("check", 5, 9, True)]


async def test_unload_unregisters(hass: HomeAssistant, entry, server: FakeServer) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    await say(hass, "check off milk on weekly shop")
    assert server.calls == []
