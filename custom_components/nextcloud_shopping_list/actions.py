"""Check off, change the amount and remove, by an item's name.

Shared by the voice sentences and the AI assistant tools, so both find the
same item and give the same answer. Each returns what to say back and never
raises.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .api import ApiConnectionError, ApiError, ApiRefused
from .coordinator import ListData, ShoppingListCoordinator
from .matching import clean_spoken, find_item
from .models import Item

UNAVAILABLE = "That list isn't available."
UNREACHABLE = "I couldn't reach Nextcloud."
REFUSED = "Nextcloud refused that."
NO_AMOUNT = "I didn't catch the amount."


def is_failure(reply: str) -> bool:
    """Whether a reply says nothing was done."""
    return reply in (UNAVAILABLE, UNREACHABLE, REFUSED, NO_AMOUNT) or reply.startswith("I couldn't find ")


@dataclass(frozen=True, slots=True)
class ListRef:
    """One shown list of one set-up Nextcloud account."""

    entry_id: str
    list_id: int


def _list(hass: HomeAssistant, ref: ListRef) -> tuple[ShoppingListCoordinator, ListData] | None:
    entry = hass.config_entries.async_get_entry(ref.entry_id)
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        return None
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data.lists.get(ref.list_id) if coordinator.data else None
    return (coordinator, data) if data is not None else None


def _find(hass: HomeAssistant, ref: ListRef, spoken: str, include_checked: bool) -> tuple[ShoppingListCoordinator, Item] | str:
    found = _list(hass, ref)
    if found is None:
        return UNAVAILABLE
    coordinator, data = found
    name = clean_spoken(spoken)
    item = find_item(data.items, name, include_checked=include_checked)
    if item is None:
        return f"I couldn't find {name} on {data.info.title}."
    return coordinator, item


async def async_check_off(hass: HomeAssistant, ref: ListRef, spoken_item: str) -> str:
    """Tick the whole item, whatever its amount."""
    found = _find(hass, ref, spoken_item, include_checked=False)
    if isinstance(found, str):
        return found
    coordinator, item = found
    try:
        await coordinator.api.async_check(ref.list_id, item.id, True)
    except ApiConnectionError:
        return UNREACHABLE
    except ApiError:
        return REFUSED
    await coordinator.async_request_refresh()
    return f"Checked off {item.name}."


async def async_change_amount(hass: HomeAssistant, ref: ListRef, spoken_item: str, amount: str) -> str:
    """Set a new amount; the server reads it and never renames the item."""
    found = _find(hass, ref, spoken_item, include_checked=False)
    if isinstance(found, str):
        return found
    coordinator, item = found
    try:
        updated = await coordinator.api.async_update_amount(ref.list_id, item.id, clean_spoken(amount))
    except ApiConnectionError:
        return UNREACHABLE
    except ApiRefused:
        return NO_AMOUNT
    except ApiError:
        return REFUSED
    await coordinator.async_request_refresh()
    return f"{updated.name} is now {updated.quantity}."


async def async_remove(hass: HomeAssistant, ref: ListRef, spoken_item: str) -> str:
    """Delete the item, looking at ticked items too."""
    found = _find(hass, ref, spoken_item, include_checked=True)
    if isinstance(found, str):
        return found
    coordinator, item = found
    try:
        await coordinator.api.async_delete(ref.list_id, item.id)
    except ApiConnectionError:
        return UNREACHABLE
    except ApiError:
        return REFUSED
    await coordinator.async_request_refresh()
    return f"Removed {item.name}."
