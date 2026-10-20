"""Finding an item by what was said, without its amount."""

from custom_components.nextcloud_shopping_list.matching import clean_spoken, find_item, fold

from .common import make_item

ITEMS = [
    make_item(1, "Milk", "2 pints"),
    make_item(2, "Bananas", "6"),
    make_item(3, "Crème fraîche"),
    make_item(4, "Tomatoes", "4"),
    make_item(5, "Bread", checked=True),
    make_item(6, "Milk", checked=True),
]


def test_fold_matches_the_app() -> None:
    assert fold("Crème Fraîche") == "creme fraiche"
    assert fold("ÄPFEL") == "apfel"


def test_matches_name_ignoring_amount_and_case() -> None:
    assert find_item(ITEMS, "milk", include_checked=False).id == 1
    assert find_item(ITEMS, "MILK", include_checked=False).id == 1


def test_singular_finds_plural() -> None:
    assert find_item(ITEMS, "banana", include_checked=False).id == 2
    assert find_item(ITEMS, "tomato", include_checked=False).id == 4


def test_accents_fold() -> None:
    assert find_item(ITEMS, "creme fraiche", include_checked=False).id == 3


def test_open_before_ticked() -> None:
    assert find_item(ITEMS, "milk", include_checked=True).id == 1
    assert find_item(ITEMS, "bread", include_checked=True).id == 5
    assert find_item(ITEMS, "bread", include_checked=False) is None


def test_no_match() -> None:
    assert find_item(ITEMS, "cheese", include_checked=True) is None


def test_clean_spoken_drops_punctuation_and_the() -> None:
    assert clean_spoken(" the milk. ") == "milk"
    assert clean_spoken("some bananas!") == "bananas"
    assert clean_spoken("three pints.") == "three pints"
    assert clean_spoken("theatre tickets") == "theatre tickets"
