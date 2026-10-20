"""Finding an item by what was said.

Home Assistant's own check-off and remove only match an item's whole text,
so "milk" never finds "2 pints Milk". This matches the item's name instead,
ignoring the amount, case, accents and an English plural.
"""

from __future__ import annotations

import re
import unicodedata

from .models import Item

_LATIN_MARKS = re.compile("[̀-ͯ]")
_LEADING_WORDS = re.compile(r"^(?:the|some|my)\s+", re.IGNORECASE)


def fold(text: str) -> str:
    """Case- and accent-insensitive, as fold() in the app."""
    return _LATIN_MARKS.sub("", unicodedata.normalize("NFD", text)).lower()


def clean_spoken(text: str) -> str:
    """What was said, without trailing punctuation from the speech engine or a leading "the"."""
    text = text.strip().rstrip(".!?,;: ").strip()
    return _LEADING_WORDS.sub("", text).strip()


def _forms(name: str) -> set[str]:
    """A name and its English singular forms, so "banana" finds "Bananas"."""
    folded = " ".join(fold(name).split())
    forms = {folded}
    if folded.endswith("es"):
        forms.add(folded[:-2])
    if folded.endswith("s"):
        forms.add(folded[:-1])
    return forms


def find_item(items: list[Item], spoken: str, *, include_checked: bool) -> Item | None:
    """The first open item called that, then the first ticked one when allowed."""
    wanted = " ".join(fold(spoken).split())
    wanted_forms = _forms(spoken)
    groups = [[i for i in items if not i.checked]]
    if include_checked:
        groups.append([i for i in items if i.checked])
    for group in groups:
        for item in group:
            if " ".join(fold(item.name).split()) == wanted:
                return item
        for item in group:
            if _forms(item.name) & wanted_forms:
                return item
    return None
