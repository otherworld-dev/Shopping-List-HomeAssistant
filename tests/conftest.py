"""Shared fixtures."""

import pytest

SERVER = "https://cloud.example.com"
BASE = SERVER + "/ocs/v2.php/apps/shopping_list/api/v1"
CAPABILITIES = SERVER + "/ocs/v2.php/cloud/capabilities"
FEATURES = ["item-images", "list-order", "invite-codes", "guest-names", "default-area", "via-label", "text-input"]


def ocs(data, status: int = 200) -> dict:
    """An OCS v2 JSON response body."""
    return {"ocs": {"meta": {"status": "ok", "statuscode": status, "message": "OK"}, "data": data}}


def item_json(**overrides) -> dict:
    """An item as the app's API returns it."""
    item = {
        "id": 7,
        "listId": 4,
        "name": "Milk",
        "quantity": "2 pints",
        "unit": None,
        "shopAreaId": 38,
        "checked": False,
        "checkedBy": None,
        "checkedByName": None,
        "checkedByGuest": False,
        "addedBy": "adam",
        "addedByName": "Adam",
        "addedByGuest": False,
        "addedVia": "Home Assistant",
        "checkedVia": None,
        "sortOrder": 0,
        "imageKey": None,
        "tags": [],
        "createdAt": "2026-10-20T08:00:00+00:00",
        "updatedAt": "2026-10-20T08:00:00+00:00",
    }
    item.update(overrides)
    return item


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    return
