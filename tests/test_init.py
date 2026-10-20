"""Setting an entry up and keeping its lists fresh."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.nextcloud_shopping_list.api import ApiAuthError, ApiConnectionError, ApiRefused
from custom_components.nextcloud_shopping_list.const import CONF_HIDDEN_LISTS, CONF_VIA_LABEL
from custom_components.nextcloud_shopping_list.models import ShoppingListInfo

from .common import FakeServer, make_entry, make_item


@pytest.fixture
def server():
    fake = FakeServer()
    with fake.patches():
        yield fake


async def test_setup_fetches_shown_lists_only(hass: HomeAssistant, server: FakeServer) -> None:
    server.lists = [ShoppingListInfo(4, "Weekly shop"), ShoppingListInfo(5, "Party")]
    server.items = {4: [make_item(7, "Milk")], 5: [make_item(9, "Crisps", list_id=5)]}
    entry = make_entry(hass, {CONF_HIDDEN_LISTS: [5]})

    assert await hass.config_entries.async_setup(entry.entry_id)

    data = entry.runtime_data.coordinator.data
    assert list(data.lists) == [4]
    assert data.lists[4].info.title == "Weekly shop"
    assert [i.name for i in data.lists[4].items] == ["Milk"]
    assert [a.name for a in data.lists[4].areas] == ["Dairy", "Bakery"]


async def test_a_list_gone_between_calls_is_skipped(hass: HomeAssistant, server: FakeServer) -> None:
    server.lists = [ShoppingListInfo(4, "Weekly shop"), ShoppingListInfo(6, "Deleted")]

    async def items(_api, list_id):
        if list_id == 6:
            raise ApiRefused("Not found")
        return []

    entry = make_entry(hass)
    with patch("custom_components.nextcloud_shopping_list.api.ShoppingListApi.async_items", items):
        assert await hass.config_entries.async_setup(entry.entry_id)

    assert list(entry.runtime_data.coordinator.data.lists) == [4]


async def test_auth_failure_starts_reauth(hass: HomeAssistant, server: FakeServer) -> None:
    server.fail = ApiAuthError("revoked")
    entry = make_entry(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_connection_error_retries_setup(hass: HomeAssistant, server: FakeServer) -> None:
    server.fail = ApiConnectionError("down")
    entry = make_entry(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_label_comes_from_the_options(hass: HomeAssistant, server: FakeServer) -> None:
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.api.via_label == "Home Assistant"


async def test_options_change_reloads_with_new_label(hass: HomeAssistant, server: FakeServer) -> None:
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(result["flow_id"], {CONF_HIDDEN_LISTS: [], CONF_VIA_LABEL: "Kitchen"})
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.api.via_label == "Kitchen"


async def test_unload(hass: HomeAssistant, server: FakeServer) -> None:
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
