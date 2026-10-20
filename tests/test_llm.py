"""The three actions as tools for AI assistants."""

import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm

from custom_components.nextcloud_shopping_list.const import CONF_HIDDEN_LISTS
from custom_components.nextcloud_shopping_list.models import ShoppingListInfo

from .common import FakeServer, make_entry, make_item

CHECK = "nextcloud_shopping_list__check_off_item"
CHANGE = "nextcloud_shopping_list__change_item_amount"
REMOVE = "nextcloud_shopping_list__remove_item"


@pytest.fixture
def server():
    fake = FakeServer()
    fake.lists = [ShoppingListInfo(4, "Weekly shop"), ShoppingListInfo(5, "Party")]
    fake.items = {4: [make_item(7, "Milk", "2 pints")], 5: [make_item(9, "Crisps", list_id=5)]}
    with fake.patches():
        yield fake


@pytest.fixture
async def entry(hass: HomeAssistant, server: FakeServer):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def context() -> llm.LLMContext:
    return llm.LLMContext(platform="test", context=Context(), language="en", assistant="conversation", device_id=None)


async def our_tools(hass: HomeAssistant) -> dict[str, llm.Tool]:
    api = await llm.async_get_api(hass, llm.LLM_API_ASSIST, context())
    return {tool.name: tool for tool in api.tools if tool.name.startswith("nextcloud_shopping_list__")}


async def call(hass: HomeAssistant, tool: llm.Tool, **args) -> llm.ToolResult:
    return await tool.async_call(hass, llm.ToolInput(tool_name=tool.name, tool_args=args), context())


def expose(hass: HomeAssistant, *entity_ids: str) -> None:
    for entity_id in entity_ids:
        async_expose_entity(hass, "conversation", entity_id, True)


async def test_tools_offered_for_exposed_lists_only(hass: HomeAssistant, entry) -> None:
    expose(hass, "todo.weekly_shop")
    async_expose_entity(hass, "conversation", "todo.party", False)

    tools = await our_tools(hass)

    assert set(tools) == {CHECK, CHANGE, REMOVE}
    assert all(tool.integration == "nextcloud_shopping_list" for tool in tools.values())
    tools[CHECK].parameters({"list": "Weekly shop", "item": "milk"})
    with pytest.raises(Exception):
        tools[CHECK].parameters({"list": "Party", "item": "crisps"})


async def test_no_tools_without_exposed_lists(hass: HomeAssistant, entry) -> None:
    async_expose_entity(hass, "conversation", "todo.weekly_shop", False)
    async_expose_entity(hass, "conversation", "todo.party", False)
    assert await our_tools(hass) == {}


async def test_check_off_tool_matches_voice(hass: HomeAssistant, entry, server: FakeServer) -> None:
    expose(hass, "todo.weekly_shop")
    result = await call(hass, (await our_tools(hass))[CHECK], list="Weekly shop", item="milk")

    assert result.data == {"response": "Checked off Milk."}
    assert not result.error
    assert server.calls == [("check", 4, 7, True)]


async def test_change_amount_tool(hass: HomeAssistant, entry, server: FakeServer) -> None:
    expose(hass, "todo.weekly_shop")
    await call(hass, (await our_tools(hass))[CHANGE], list="Weekly shop", item="milk", amount="three pints")
    assert server.calls == [("update_amount", 4, 7, "three pints")]


async def test_not_found_is_an_error_result(hass: HomeAssistant, entry, server: FakeServer) -> None:
    expose(hass, "todo.weekly_shop")
    result = await call(hass, (await our_tools(hass))[REMOVE], list="Weekly shop", item="cheese")

    assert result.error
    assert result.data == {"response": "I couldn't find cheese on Weekly shop."}
    assert server.calls == []


async def test_two_entries_one_tool_set(hass: HomeAssistant, server: FakeServer) -> None:
    first = make_entry(hass, {CONF_HIDDEN_LISTS: [5]})
    make_entry(hass, {CONF_HIDDEN_LISTS: [4]}, login="sam")
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    expose(hass, "todo.weekly_shop", "todo.party")

    tools = await our_tools(hass)

    assert set(tools) == {CHECK, CHANGE, REMOVE}
    await call(hass, tools[CHECK], list="Party", item="crisps")
    assert server.calls == [("check", 5, 9, True)]
