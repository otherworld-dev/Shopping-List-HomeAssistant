"""What the Shopping List app's API sends back."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class ShoppingListInfo:
    """A list the account can see, its own or shared with it."""

    id: int
    title: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(id=int(data["id"]), title=str(data.get("title") or ""))


@dataclass(frozen=True, slots=True)
class Area:
    """A shop area of a list, such as Dairy."""

    id: int
    name: str
    sort_order: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(id=int(data["id"]), name=str(data.get("name") or ""), sort_order=int(data.get("sortOrder") or 0))


@dataclass(frozen=True, slots=True)
class Item:
    """An item on a list."""

    id: int
    list_id: int
    name: str
    quantity: str | None
    unit: str | None
    shop_area_id: int | None
    checked: bool
    sort_order: int
    added_by_name: str | None
    added_via: str | None
    checked_by_name: str | None
    checked_via: str | None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        area = data.get("shopAreaId")
        return cls(
            id=int(data["id"]),
            list_id=int(data.get("listId") or 0),
            name=str(data.get("name") or ""),
            quantity=data.get("quantity"),
            unit=data.get("unit"),
            shop_area_id=int(area) if area is not None else None,
            checked=bool(data.get("checked")),
            sort_order=int(data.get("sortOrder") or 0),
            added_by_name=data.get("addedByName"),
            added_via=data.get("addedVia"),
            checked_by_name=data.get("checkedByName"),
            checked_via=data.get("checkedVia"),
        )
