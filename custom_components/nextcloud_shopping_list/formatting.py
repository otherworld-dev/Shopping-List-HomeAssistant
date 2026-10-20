"""How items read in Home Assistant's to-do card, as close to the app as it allows.

The card has one line of text per item and an optional grey line under it,
and no headings, so the shop area moves to the grey line along with who
added or ticked the item.
"""

from __future__ import annotations

from .models import Area, Item


def item_summary(item: Item) -> str:
    """The amount, then the name, as the app's item row shows them ("2 pints Milk")."""
    if not item.quantity:
        return item.name
    amount = f"{item.quantity} {item.unit}" if item.unit else item.quantity
    return f"{amount} {item.name}"


def item_description(item: Item, areas: dict[int, Area]) -> str | None:
    """The shop area, then who added it, or who ticked it once ticked ("Dairy · Adam")."""
    parts: list[str] = []
    if item.shop_area_id is not None and (area := areas.get(item.shop_area_id)) is not None:
        parts.append(area.name)
    if item.checked:
        if who := item.checked_via or item.checked_by_name:
            parts.append(f"ticked by {who}")
    elif who := item.added_via or item.added_by_name:
        parts.append(who)
    return " · ".join(parts) or None


def ordered_items(items: list[Item], areas: list[Area]) -> list[Item]:
    """Open items grouped by shop area in the list's order, as the app's default view.

    Items with no area, or one the list no longer has, come after the areas.
    Inside each group the server's order stays, which is the order people
    dragged them into. Ticked items follow, in the same area order.
    """
    rank = {area.id: index for index, area in enumerate(sorted(areas, key=lambda a: a.sort_order))}
    last = len(rank)

    def area_rank(item: Item) -> int:
        return rank.get(item.shop_area_id, last) if item.shop_area_id is not None else last

    open_items = sorted((i for i in items if not i.checked), key=area_rank)
    ticked = sorted((i for i in items if i.checked), key=area_rank)
    return open_items + ticked
