"""Check off, change and remove by voice.

Home Assistant's own sentences for these only match an item's whole text,
so these are registered as sentence triggers, which Home Assistant tries
before its own sentences and before any AI assistant. The sentences carry
the lists' spoken names, so a sentence naming any other to-do list never
reaches us and Home Assistant handles it as usual.

One registrar covers every set-up account, so a name is only ever acted on
once: a list two accounts can both see is one list, and a name two
different lists share is refused rather than acted on twice.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable

from hassil.recognize import RecognizeResult
from homeassistant.components.conversation import ConversationInput
from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util.hass_dict import HassKey
from yarl import URL

from .actions import ListRef, async_change_amount, async_check_off, async_remove
from .const import CONF_SERVER, DOMAIN
from .coordinator import ShoppingListConfigEntry
from .todo import list_unique_id

# English for now; {item} and {amount} are what was said, (<names>) the lists' names.
# "in" only comes with "list", so "set the brightness to 50 percent in the
# kitchen" stays a command for the kitchen's lights when a list is called Kitchen.
COMMANDS: dict[str, list[str]] = {
    "check": [
        "(check|tick) off [the] {item} (on|from) [the] (<names>) [list]",
        "(check|tick) off [the] {item} in [the] (<names>) list",
        "mark [the] {item} as (done|bought) on [the] (<names>) [list]",
    ],
    "change": [
        "(change|set) [the] {item} to {amount} on [the] (<names>) [list]",
        "(change|set) [the] {item} to {amount} in [the] (<names>) list",
    ],
    "remove": [
        "(remove|delete) [the] {item} from [the] (<names>) [list]",
    ],
}

AMBIGUOUS = (
    "There's more than one list called that, so I've left them alone. "
    "Give one of them another name in Home Assistant."
)

DATA_VOICE: HassKey[VoiceRegistrar] = HassKey(f"{DOMAIN}_voice")


def spoken_name(title: str) -> str:
    """A list name as it can be said and written into a sentence template."""
    text = re.sub(r"['’]", "", title.lower())
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def spoken_forms(name: str) -> set[str]:
    """Every way a name may arrive: "Mum's list" as "mum's list", "mum’s list" or "mums list"."""
    text = name.lower().replace("’", "'")
    text = " ".join(re.sub(r"[^\w\s']", " ", text).split())
    # Only apostrophes inside a word are kept
    text = " ".join(re.sub(r"(?<!\w)'|'(?!\w)", " ", text).split())
    forms = {text.replace("'", "")}
    if "'" in text:
        forms.update({text, text.replace("'", "’")})
    forms.discard("")
    return forms


def sentences_for(command: str, names: list[str]) -> list[str]:
    alternatives = "|".join(names)
    return [template.replace("<names>", alternatives) for template in COMMANDS[command]]


def _server_key(entry: ShoppingListConfigEntry) -> str:
    """The same list seen through two accounts has the same server and id."""
    url = URL(entry.data[CONF_SERVER])
    return f"{(url.host or '').lower()}:{url.port}{url.path.rstrip('/')}"


def _handler(hass: HomeAssistant, ref: ListRef, command: str):
    async def handle(user_input: ConversationInput, result: RecognizeResult) -> str:
        item = str(result.entities["item"].value)
        if command == "check":
            return await async_check_off(hass, ref, item)
        if command == "change":
            return await async_change_amount(hass, ref, item, str(result.entities["amount"].value))
        return await async_remove(hass, ref, item)

    return handle


async def _ambiguous(user_input: ConversationInput, result: RecognizeResult) -> str:
    return AMBIGUOUS


class VoiceRegistrar:
    """The sentences for every loaded account's lists, rebuilt whenever they change."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._entries: dict[str, ShoppingListConfigEntry] = {}
        self._unregister: list[Callable[[], None]] = []

    @callback
    def add(self, entry: ShoppingListConfigEntry) -> None:
        self._entries[entry.entry_id] = entry
        self.rebuild()

    @callback
    def remove(self, entry_id: str) -> None:
        self._entries.pop(entry_id, None)
        self.rebuild()

    @callback
    def _names(self, registry: er.EntityRegistry, entry: ShoppingListConfigEntry, list_id: int, title: str) -> list[str]:
        """The list's spoken names: its aliases, and its own name unless that was taken off."""
        entity_id = registry.async_get_entity_id(Platform.TODO, DOMAIN, list_unique_id(entry, list_id))
        entity = registry.async_get(entity_id) if entity_id else None
        if entity is None or not entity.aliases:
            return [title]
        # The title from the server rather than the registry's copy of the name, so a rename counts at once
        return [title if alias is er.COMPUTED_NAME else alias for alias in entity.aliases if isinstance(alias, str) or alias is er.COMPUTED_NAME]

    @callback
    def rebuild(self) -> None:
        for unregister in self._unregister:
            unregister()
        self._unregister.clear()

        registry = er.async_get(self._hass)
        refs: dict[tuple[str, int], ListRef] = {}
        lists_by_form: dict[str, set[tuple[str, int]]] = defaultdict(set)
        for entry in self._entries.values():
            coordinator = entry.runtime_data.coordinator
            if not coordinator.data:
                continue
            server = _server_key(entry)
            for list_id, data in coordinator.data.lists.items():
                key = (server, list_id)
                refs.setdefault(key, ListRef(entry_id=entry.entry_id, list_id=list_id))
                for name in self._names(registry, entry, list_id, data.info.title):
                    for form in spoken_forms(name):
                        lists_by_form[form].add(key)

        forms_by_list: dict[tuple[str, int], list[str]] = defaultdict(list)
        ambiguous: list[str] = []
        for form, keys in lists_by_form.items():
            if len(keys) == 1:
                forms_by_list[next(iter(keys))].append(form)
            else:
                ambiguous.append(form)

        manager = get_agent_manager(self._hass)
        for key, forms in forms_by_list.items():
            for command in COMMANDS:
                self._unregister.append(
                    manager.register_trigger(sentences_for(command, sorted(forms)), _handler(self._hass, refs[key], command))
                )
        if ambiguous:
            for command in COMMANDS:
                self._unregister.append(manager.register_trigger(sentences_for(command, sorted(ambiguous)), _ambiguous))


@callback
def async_entry_loaded(hass: HomeAssistant, entry: ShoppingListConfigEntry) -> None:
    """Add the account's lists to the sentences, and keep them in step with its lists and their aliases."""
    if DATA_VOICE not in hass.data:
        hass.data[DATA_VOICE] = VoiceRegistrar(hass)
    registrar = hass.data[DATA_VOICE]
    coordinator = entry.runtime_data.coordinator

    def current_lists() -> tuple:
        lists = coordinator.data.lists if coordinator.data else {}
        return tuple(sorted((list_id, data.info.title) for list_id, data in lists.items()))

    seen = [current_lists()]

    @callback
    def lists_changed() -> None:
        if (lists := current_lists()) != seen[0]:
            seen[0] = lists
            registrar.rebuild()

    @callback
    def is_ours(event_data: er.EventEntityRegistryUpdatedData) -> bool:
        entity = er.async_get(hass).async_get(event_data["entity_id"])
        return entity is not None and entity.config_entry_id == entry.entry_id

    @callback
    def entity_changed(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        registrar.rebuild()

    @callback
    def unload() -> None:
        registrar.remove(entry.entry_id)

    registrar.add(entry)
    entry.async_on_unload(coordinator.async_add_listener(lists_changed))
    entry.async_on_unload(hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, entity_changed, event_filter=is_ours))
    entry.async_on_unload(unload)
