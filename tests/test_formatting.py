"""Items read the way the app's own list shows them."""

from custom_components.nextcloud_shopping_list.formatting import item_description, item_summary, ordered_items
from custom_components.nextcloud_shopping_list.models import Area

from .common import make_item

DAIRY = Area(38, "Dairy", 2)
FRUIT = Area(37, "Fruit & veg", 1)
AREAS = {a.id: a for a in (DAIRY, FRUIT)}


def test_summary_matches_the_app() -> None:
    assert item_summary(make_item(1, "Bananas", "6")) == "6 Bananas"
    assert item_summary(make_item(2, "Bread", "1")) == "1 Bread"
    assert item_summary(make_item(3, "Milk", "2 pints")) == "2 pints Milk"
    assert item_summary(make_item(4, "Cheddar", "500 g")) == "500 g Cheddar"
    assert item_summary(make_item(5, "Bread", None)) == "Bread"
    assert item_summary(make_item(6, "Bread", "")) == "Bread"


def test_unit_field_is_shown() -> None:
    assert item_summary(make_item(1, "Flour", "2", unit="cups")) == "2 cups Flour"
    # As in the app, a unit with no amount isn't shown
    assert item_summary(make_item(2, "Flour", None, unit="cups")) == "Flour"


def test_description_area_and_adder() -> None:
    assert item_description(make_item(1, "Milk", shop_area_id=38), AREAS) == "Dairy · Adam"


def test_description_prefers_via() -> None:
    assert item_description(make_item(1, "Milk", shop_area_id=38, added_via="Home Assistant"), AREAS) == "Dairy · Home Assistant"


def test_description_ticked() -> None:
    item = make_item(1, "Eggs", shop_area_id=38, checked=True, checked_by_name="Sam")
    assert item_description(item, AREAS) == "Dairy · ticked by Sam"
    via = make_item(1, "Eggs", shop_area_id=38, checked=True, checked_by_name="Adam", checked_via="Home Assistant")
    assert item_description(via, AREAS) == "Dairy · ticked by Home Assistant"


def test_description_no_area() -> None:
    assert item_description(make_item(1, "Milk"), AREAS) == "Adam"
    # An area the list no longer has is treated as none
    assert item_description(make_item(1, "Milk", shop_area_id=99), AREAS) == "Adam"
    assert item_description(make_item(1, "Milk", added_by_name=None), AREAS) is None


def test_order_follows_area_order_then_unassigned() -> None:
    items = [
        make_item(1, "Batteries"),
        make_item(2, "Milk", shop_area_id=38),
        make_item(3, "Bananas", shop_area_id=37),
        make_item(4, "Cheddar", shop_area_id=38),
        make_item(5, "Old", shop_area_id=99),
    ]
    assert [i.id for i in ordered_items(items, [DAIRY, FRUIT])] == [3, 2, 4, 1, 5]


def test_ticked_after_open() -> None:
    items = [
        make_item(1, "Eggs", shop_area_id=38, checked=True),
        make_item(2, "Milk", shop_area_id=38),
        make_item(3, "Apples", shop_area_id=37, checked=True),
        make_item(4, "Bread"),
    ]
    assert [i.id for i in ordered_items(items, [DAIRY, FRUIT])] == [2, 4, 3, 1]
