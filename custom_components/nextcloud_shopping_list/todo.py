"""Each shown shopping list as a Home Assistant to-do list."""

from __future__ import annotations

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ApiError
from .const import DOMAIN
from .coordinator import ListData, ShoppingListConfigEntry, ShoppingListCoordinator
from .formatting import item_description, item_summary, ordered_items
from .models import Item


def list_unique_id(entry: ShoppingListConfigEntry, list_id: int) -> str:
    return f"{entry.unique_id}_{list_id}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ShoppingListConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[int] = set()

    @callback
    def sync_lists() -> None:
        """Add a to-do list for each new list, and drop the ones that are gone or hidden."""
        current = set(coordinator.data.lists) if coordinator.data else set()
        new = current - known
        gone = known - current
        if gone:
            registry = er.async_get(hass)
            for list_id in gone:
                if entity_id := registry.async_get_entity_id(Platform.TODO, DOMAIN, list_unique_id(entry, list_id)):
                    registry.async_remove(entity_id)
            known.difference_update(gone)
        if new:
            known.update(new)
            async_add_entities(ShoppingListTodo(coordinator, entry, list_id) for list_id in sorted(new))

    sync_lists()
    entry.async_on_unload(coordinator.async_add_listener(sync_lists))


class ShoppingListTodo(CoordinatorEntity[ShoppingListCoordinator], TodoListEntity):
    """One shopping list."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
    )

    def __init__(self, coordinator: ShoppingListCoordinator, entry: ShoppingListConfigEntry, list_id: int) -> None:
        super().__init__(coordinator)
        self.list_id = list_id
        self._attr_unique_id = list_unique_id(entry, list_id)

    @property
    def _data(self) -> ListData | None:
        return self.coordinator.data.lists.get(self.list_id) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self._data is not None

    @property
    def name(self) -> str | None:
        # The list's own title, kept up to date when it is renamed in the app
        data = self._data
        return data.info.title if data else None

    @property
    def todo_items(self) -> list[TodoItem] | None:
        data = self._data
        if data is None:
            return None
        areas = {area.id: area for area in data.areas}
        return [
            TodoItem(
                uid=str(item.id),
                summary=item_summary(item),
                status=TodoItemStatus.COMPLETED if item.checked else TodoItemStatus.NEEDS_ACTION,
                description=item_description(item, areas),
            )
            for item in ordered_items(data.items, data.areas)
        ]

    def _item(self, uid: str | None) -> Item:
        data = self._data
        for item in data.items if data else []:
            if str(item.id) == uid:
                return item
        raise HomeAssistantError(f"Item {uid} is no longer on the list")

    async def _async_write(self, call) -> None:
        """Run a change, then refresh so the card shows what the server made of it."""
        try:
            await call
        except ApiError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            await self.coordinator.async_request_refresh()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        # The server reads the amount, files it in its area and merges a duplicate
        await self._async_write(self.coordinator.api.async_add_text(self.list_id, item.summary or ""))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        current = self._item(item.uid)
        checked = item.status == TodoItemStatus.COMPLETED
        api = self.coordinator.api

        async def changes() -> None:
            if item.summary is not None and item.summary != item_summary(current):
                await api.async_update_text(self.list_id, current.id, item.summary)
            if checked != current.checked:
                await api.async_check(self.list_id, current.id, checked)

        await self._async_write(changes())

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        data = self._data
        ticked = {str(item.id) for item in data.items if item.checked} if data else set()
        api = self.coordinator.api

        async def changes() -> None:
            # "Remove completed items" is the app's "clear checked"
            if ticked and set(uids) == ticked:
                await api.async_clear_checked(self.list_id)
                return
            for uid in uids:
                await api.async_delete(self.list_id, self._item(uid).id)

        await self._async_write(changes())

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        """Change the order only: an item dragged among another area's items keeps its own area."""
        data = self._data
        if data is None:
            return
        order = [str(item.id) for item in ordered_items(data.items, data.areas) if not item.checked]
        if uid not in order:
            return
        order.remove(uid)
        order.insert(order.index(previous_uid) + 1 if previous_uid in order else 0, uid)
        await self._async_write(self.coordinator.api.async_reorder(self.list_id, [int(i) for i in order]))
