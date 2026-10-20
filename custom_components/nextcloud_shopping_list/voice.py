"""Check off, change and remove by voice.

Home Assistant's own sentences for these only match an item's whole text,
so these are registered as sentence triggers, which Home Assistant tries
before its own sentences and before any AI assistant. Each list gets its
own sentences with its name and aliases written in, so a sentence naming
any other to-do list never reaches us and Home Assistant handles it as usual.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant.components.conversation import ConversationInput
from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from hassil.recognize import RecognizeResult

from .actions import ListRef, async_change_amount, async_check_off, async_remove
from .const import DOMAIN
from .coordinator import ShoppingListConfigEntry
from .todo import list_unique_id

# English for now; {item} and {amount} are what was said, (<names>) the list's names
COMMANDS: dict[str, list[str]] = {
    "check": [
        "(check|tick) off [the] {item} (on|from|in) [the] (<names>) [list]",
        "mark [the] {item} as (done|bought) (on|in) [the] (<names>) [list]",
    ],
    "change": [
        "(change|set) [the] {item} to {amount} (on|in) [the] (<names>) [list]",
    ],
    "remove": [
        "(remove|delete) [the] {item} from [the] (<names>) [list]",
    ],
}


def spoken_name(title: str) -> str:
    """A list name as it can be said and written into a sentence template."""
    text = re.sub(r"['’]", "", title.lower())
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def sentences_for(command: str, names: list[str]) -> list[str]:
    alternatives = "|".join(names)
    return [template.replace("<names>", alternatives) for template in COMMANDS[command]]


@dataclass
class _EntryVoice:
    """What one set-up account has registered."""

    unregister: list[Callable[[], None]] = field(default_factory=list)
    lists: tuple = ()


def _handler(hass: HomeAssistant, ref: ListRef, command: str):
    async def handle(user_input: ConversationInput, result: RecognizeResult) -> str:
        item = str(result.entities["item"].value)
        if command == "check":
            return await async_check_off(hass, ref, item)
        if command == "change":
            return await async_change_amount(hass, ref, item, str(result.entities["amount"].value))
        return await async_remove(hass, ref, item)

    return handle


@callback
def _register(hass: HomeAssistant, entry: ShoppingListConfigEntry, state: _EntryVoice) -> None:
    for unregister in state.unregister:
        unregister()
    state.unregister.clear()

    coordinator = entry.runtime_data.coordinator
    if not coordinator.data:
        return
    registry = er.async_get(hass)
    manager = get_agent_manager(hass)
    for list_id, data in coordinator.data.lists.items():
        names = {spoken_name(data.info.title)}
        entity_id = registry.async_get_entity_id(Platform.TODO, DOMAIN, list_unique_id(entry, list_id))
        if entity_id and (entity := registry.async_get(entity_id)):
            # Extra spoken names given in Home Assistant, such as "shopping list"
            names.update(spoken_name(alias) for alias in entity.aliases if isinstance(alias, str))
        names.discard("")
        if not names:
            continue
        ref = ListRef(entry_id=entry.entry_id, list_id=list_id)
        for command in COMMANDS:
            state.unregister.append(
                manager.register_trigger(sentences_for(command, sorted(names)), _handler(hass, ref, command))
            )


@callback
def async_entry_loaded(hass: HomeAssistant, entry: ShoppingListConfigEntry) -> None:
    """Register the account's sentences, and keep them in step with its lists and their aliases."""
    state = _EntryVoice()
    coordinator = entry.runtime_data.coordinator

    def current_lists() -> tuple:
        lists = coordinator.data.lists if coordinator.data else {}
        return tuple(sorted((list_id, data.info.title) for list_id, data in lists.items()))

    state.lists = current_lists()
    _register(hass, entry, state)

    @callback
    def lists_changed() -> None:
        if (lists := current_lists()) != state.lists:
            state.lists = lists
            _register(hass, entry, state)

    @callback
    def is_ours(event_data: er.EventEntityRegistryUpdatedData) -> bool:
        entity = er.async_get(hass).async_get(event_data["entity_id"])
        return entity is not None and entity.config_entry_id == entry.entry_id

    @callback
    def entity_changed(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        _register(hass, entry, state)

    @callback
    def unload() -> None:
        for unregister in state.unregister:
            unregister()
        state.unregister.clear()

    entry.async_on_unload(coordinator.async_add_listener(lists_changed))
    entry.async_on_unload(hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, entity_changed, event_filter=is_ours))
    entry.async_on_unload(unload)
