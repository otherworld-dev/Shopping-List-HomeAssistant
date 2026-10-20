"""The three actions as tools for AI assistants.

The voice sentences run before any AI assistant, but someone talking freely
("I've got the milk, tick it off") goes to the AI. Home Assistant already
gives it tools to read lists and add items; these let it check off, change
the amount and remove by an item's name, as the sentences do.
"""

from __future__ import annotations

from typing import Any, override

import probatio
from homeassistant.components.homeassistant import async_should_expose
from homeassistant.components.llm import LLMTools
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, intent
from homeassistant.helpers.llm import (
    LLM_API_ASSIST,
    LLMContext,
    Tool,
    ToolAnnotations,
    ToolInput,
    ToolResult,
)

from .actions import ListRef, async_change_amount, async_check_off, async_remove, is_failure
from .const import DOMAIN
from .todo import list_unique_id

ITEM = "The item's name as it is on the list, without its amount, for example milk"


class _ListTool(Tool):
    """A tool acting on one item of one of the exposed lists."""

    integration = DOMAIN

    def __init__(self, lists: dict[str, ListRef]) -> None:
        self._lists = lists
        self.parameters = probatio.Schema(self._schema(sorted(lists)))

    def _schema(self, names: list[str]) -> dict[Any, Any]:
        return {
            probatio.Required("list", description="The shopping list"): probatio.In(names),
            probatio.Required("item", description=ITEM): str,
        }

    async def _act(self, hass: HomeAssistant, ref: ListRef, args: dict[str, Any]) -> str:
        raise NotImplementedError

    @override
    async def async_call(self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext) -> ToolResult:
        args = self.parameters(tool_input.tool_args)
        reply = await self._act(hass, self._lists[args["list"]], args)
        return ToolResult(data={"response": reply}, error=is_failure(reply))


class CheckOffTool(_ListTool):
    name = f"{DOMAIN}__check_off_item"
    title = "Check off a shopping list item"
    description = "Tick off a whole item on a Nextcloud shopping list. Give the item's name without its amount."
    annotations = ToolAnnotations(destructive=False, idempotent=True)

    async def _act(self, hass: HomeAssistant, ref: ListRef, args: dict[str, Any]) -> str:
        return await async_check_off(hass, ref, args["item"])


class ChangeAmountTool(_ListTool):
    name = f"{DOMAIN}__change_item_amount"
    title = "Change how much of a shopping list item is needed"
    description = "Change how much of an item a Nextcloud shopping list needs, for example 3 pints."
    annotations = ToolAnnotations(destructive=False, idempotent=True)

    def _schema(self, names: list[str]) -> dict[Any, Any]:
        return super()._schema(names) | {
            probatio.Required("amount", description="The new amount, for example 3 pints or six"): str
        }

    async def _act(self, hass: HomeAssistant, ref: ListRef, args: dict[str, Any]) -> str:
        return await async_change_amount(hass, ref, args["item"], args["amount"])


class RemoveTool(_ListTool):
    name = f"{DOMAIN}__remove_item"
    title = "Remove a shopping list item"
    description = "Remove an item from a Nextcloud shopping list."

    async def _act(self, hass: HomeAssistant, ref: ListRef, args: dict[str, Any]) -> str:
        return await async_remove(hass, ref, args["item"])


@callback
def _exposed_lists(hass: HomeAssistant, assistant: str) -> dict[str, ListRef]:
    """Every name, with aliases, of every list exposed to the assistant, across all set-up accounts."""
    registry = er.async_get(hass)
    lists: dict[str, ListRef] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED or not entry.runtime_data.coordinator.data:
            continue
        for list_id in sorted(entry.runtime_data.coordinator.data.lists):
            entity_id = registry.async_get_entity_id(Platform.TODO, DOMAIN, list_unique_id(entry, list_id))
            if entity_id is None or not async_should_expose(hass, assistant, entity_id):
                continue
            state = hass.states.get(entity_id)
            for name in intent.async_get_entity_aliases(hass, registry.async_get(entity_id), state=state):
                lists.setdefault(name, ListRef(entry_id=entry.entry_id, list_id=list_id))
    return lists


@callback
def async_get_tools(hass: HomeAssistant, llm_context: LLMContext, api_id: str) -> LLMTools | None:
    """The tools, when at least one list is exposed to the assistant."""
    if api_id != LLM_API_ASSIST:
        return None
    lists = _exposed_lists(hass, llm_context.assistant)
    if not lists:
        return None
    return LLMTools(tools=[CheckOffTool(lists), ChangeAmountTool(lists), RemoveTool(lists)])
