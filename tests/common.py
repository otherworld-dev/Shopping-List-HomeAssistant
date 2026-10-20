"""Helpers for setting up an entry against a fake Shopping List server."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nextcloud_shopping_list.const import (
    CONF_APP_PASSWORD,
    CONF_LOGIN_NAME,
    CONF_SERVER,
    DOMAIN,
)
from custom_components.nextcloud_shopping_list.models import Area, Item, ShoppingListInfo

from .conftest import SERVER

API = "custom_components.nextcloud_shopping_list.api.ShoppingListApi"


def make_item(item_id: int, name: str, quantity: str | None = "1", **kw) -> Item:
    fields = {
        "id": item_id,
        "list_id": 4,
        "name": name,
        "quantity": quantity,
        "unit": None,
        "shop_area_id": None,
        "checked": False,
        "sort_order": 0,
        "added_by_name": "Adam",
        "added_via": None,
        "checked_by_name": None,
        "checked_via": None,
    }
    fields.update(kw)
    return Item(**fields)


class FakeServer:
    """What the Shopping List app holds, served through patched API methods."""

    def __init__(self) -> None:
        self.lists: list[ShoppingListInfo] = [ShoppingListInfo(4, "Weekly shop")]
        self.items: dict[int, list[Item]] = {4: []}
        self.areas: dict[int, list[Area]] = {4: [Area(38, "Dairy", 1), Area(39, "Bakery", 2)]}
        self.calls: list[tuple] = []
        self.fail: Exception | None = None

    async def lists_(self, *_):
        if self.fail:
            raise self.fail
        return list(self.lists)

    # Bound methods patched onto the class aren't bound again, so no api argument
    async def items_(self, list_id):
        return list(self.items.get(list_id, []))

    async def areas_(self, list_id):
        return list(self.areas.get(list_id, []))

    def recorder(self, name: str, result=None):
        async def record(_api, *args):
            self.calls.append((name, *args))
            return result(*args) if callable(result) else result

        return record

    def patches(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch(f"{API}.async_lists", self.lists_))
        stack.enter_context(patch(f"{API}.async_items", self.items_))
        stack.enter_context(patch(f"{API}.async_areas", self.areas_))
        for name in ("add_text", "update_text", "update_amount", "check", "delete", "clear_checked", "reorder"):
            stack.enter_context(patch(f"{API}.async_{name}", self.recorder(name, make_item(7, "Milk"))))
        stack.enter_context(patch(f"{API}.async_features", AsyncMock(return_value=("1.13.0", ["text-input", "via-label"]))))
        return stack


def make_entry(hass: HomeAssistant, options: dict | None = None, login: str = "adam") -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{login}@cloud.example.com",
        title=f"{login} on cloud.example.com",
        data={CONF_SERVER: SERVER, CONF_LOGIN_NAME: login, CONF_APP_PASSWORD: "secret"},
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry
