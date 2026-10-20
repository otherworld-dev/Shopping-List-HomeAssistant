"""Check off, change the amount and remove, by an item's name."""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.nextcloud_shopping_list.actions import (
    ListRef,
    async_change_amount,
    async_check_off,
    async_remove,
)
from custom_components.nextcloud_shopping_list.api import ApiConnectionError, ApiRefused

from .common import API, FakeServer, make_entry, make_item


@pytest.fixture
def server():
    fake = FakeServer()
    fake.items = {
        4: [
            make_item(7, "Milk", "2 pints"),
            make_item(8, "Bananas", "6"),
            make_item(9, "Eggs", "12", checked=True),
        ]
    }
    with fake.patches():
        yield fake


@pytest.fixture
async def ref(hass: HomeAssistant, server: FakeServer) -> ListRef:
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return ListRef(entry_id=entry.entry_id, list_id=4)


async def test_check_off_ticks_the_whole_item(hass: HomeAssistant, ref: ListRef, server: FakeServer) -> None:
    assert await async_check_off(hass, ref, "milk") == "Checked off Milk."
    assert server.calls == [("check", 4, 7, True)]


async def test_check_off_ignores_the_and_punctuation(hass: HomeAssistant, ref: ListRef, server: FakeServer) -> None:
    assert await async_check_off(hass, ref, "the banana.") == "Checked off Bananas."
    assert server.calls == [("check", 4, 8, True)]


async def test_check_off_missing_or_already_ticked_sends_nothing(hass: HomeAssistant, ref: ListRef, server: FakeServer) -> None:
    assert await async_check_off(hass, ref, "cheese") == "I couldn't find cheese on Weekly shop."
    assert await async_check_off(hass, ref, "eggs") == "I couldn't find eggs on Weekly shop."
    assert server.calls == []


async def test_change_amount_sends_amount_only(hass: HomeAssistant, ref: ListRef, server: FakeServer) -> None:
    async def updated(_api, list_id, item_id, amount):
        server.calls.append(("update_amount", list_id, item_id, amount))
        return make_item(7, "Milk", "3 pints")

    with patch(f"{API}.async_update_amount", updated):
        assert await async_change_amount(hass, ref, "milk", "three pints.") == "Milk is now 3 pints."
    assert server.calls == [("update_amount", 4, 7, "three pints")]


async def test_unreadable_amount_reply(hass: HomeAssistant, ref: ListRef) -> None:
    async def refuse(_api, *args):
        raise ApiRefused("That is not an amount")

    with patch(f"{API}.async_update_amount", refuse):
        assert await async_change_amount(hass, ref, "milk", "lots") == "I didn't catch the amount."


async def test_remove_finds_ticked_items_too(hass: HomeAssistant, ref: ListRef, server: FakeServer) -> None:
    assert await async_remove(hass, ref, "eggs") == "Removed Eggs."
    assert server.calls == [("delete", 4, 9)]


async def test_unreachable_reply(hass: HomeAssistant, ref: ListRef) -> None:
    async def down(_api, *args):
        raise ApiConnectionError("down")

    with patch(f"{API}.async_check", down):
        assert await async_check_off(hass, ref, "milk") == "I couldn't reach Nextcloud."


async def test_a_list_that_is_gone(hass: HomeAssistant, ref: ListRef, server: FakeServer) -> None:
    assert await async_check_off(hass, ListRef(ref.entry_id, 99), "milk") == "That list isn't available."
    assert await async_check_off(hass, ListRef("nope", 4), "milk") == "That list isn't available."
    assert server.calls == []
