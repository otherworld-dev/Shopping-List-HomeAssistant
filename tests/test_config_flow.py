"""Setting the integration up, signing in again, and its options."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nextcloud_shopping_list.api import ApiConnectionError
from custom_components.nextcloud_shopping_list.const import (
    CONF_APP_PASSWORD,
    CONF_HIDDEN_LISTS,
    CONF_LOGIN_NAME,
    CONF_SERVER,
    CONF_VIA_LABEL,
    DOMAIN,
)
from custom_components.nextcloud_shopping_list.login_flow import Credentials, LoginStart
from custom_components.nextcloud_shopping_list.models import ShoppingListInfo

from .conftest import FEATURES, SERVER

FLOW = "custom_components.nextcloud_shopping_list.config_flow"
START = LoginStart(login_url=f"{SERVER}/index.php/login/v2/flow/abc", poll_endpoint=f"{SERVER}/poll", token="tok")
CREDS = Credentials(server=SERVER, login_name="adam", app_password="secret")


@pytest.fixture(autouse=True)
def no_setup():
    """Creating an entry must not try to set it up for real."""
    with patch("custom_components.nextcloud_shopping_list.async_setup_entry", return_value=True):
        yield


@pytest.fixture
def features():
    with patch(f"{FLOW}.ShoppingListApi.async_features", AsyncMock(return_value=("1.13.0", FEATURES))) as mock:
        yield mock


async def _to_method_menu(hass: HomeAssistant, server: str = "cloud.example.com") -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SERVER: server})
    assert result["type"] is FlowResultType.MENU
    return result


async def test_login_flow_creates_entry(hass: HomeAssistant, features) -> None:
    with (
        patch(f"{FLOW}.login_flow.async_start", AsyncMock(return_value=START)) as start,
        patch(f"{FLOW}.login_flow.async_poll", AsyncMock(return_value=CREDS)),
        patch(f"{FLOW}.POLL_INTERVAL", 0),
    ):
        result = await _to_method_menu(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "auth"})
        assert result["type"] is FlowResultType.EXTERNAL_STEP
        assert result["url"] == START.login_url
        # A bare host is taken as https
        assert start.call_args.args[1] == SERVER

        # The wait for access runs in the background, as it can take minutes
        await hass.async_block_till_done(wait_background_tasks=True)
        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "adam on cloud.example.com"
    assert result["data"] == {CONF_SERVER: SERVER, CONF_LOGIN_NAME: "adam", CONF_APP_PASSWORD: "secret"}
    assert result["result"].unique_id == "adam@cloud.example.com"


async def test_manual_creates_entry(hass: HomeAssistant, features) -> None:
    result = await _to_method_menu(hass, "https://cloud.example.com/")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "manual"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOGIN_NAME: "adam", CONF_APP_PASSWORD: "secret"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_SERVER: SERVER, CONF_LOGIN_NAME: "adam", CONF_APP_PASSWORD: "secret"}


async def _manual(hass: HomeAssistant) -> dict:
    result = await _to_method_menu(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "manual"})
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOGIN_NAME: "adam", CONF_APP_PASSWORD: "secret"}
    )


async def test_server_too_old_aborts(hass: HomeAssistant) -> None:
    with patch(f"{FLOW}.ShoppingListApi.async_features", AsyncMock(return_value=("1.12.0", ["default-area"]))):
        result = await _manual(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "server_too_old"
    assert result["description_placeholders"]["version"] == "1.13.0"


async def test_missing_app_aborts(hass: HomeAssistant) -> None:
    with patch(f"{FLOW}.ShoppingListApi.async_features", AsyncMock(return_value=(None, []))):
        result = await _manual(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "missing_app"


async def test_unreachable_server_shows_an_error(hass: HomeAssistant) -> None:
    with patch(f"{FLOW}.login_flow.async_start", AsyncMock(side_effect=ApiConnectionError("down"))):
        result = await _to_method_menu(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "auth"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_aborts(hass: HomeAssistant, features) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="adam@cloud.example.com").add_to_hass(hass)
    result = await _manual(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_password(hass: HomeAssistant, features) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="adam@cloud.example.com",
        data={CONF_SERVER: SERVER, CONF_LOGIN_NAME: "adam", CONF_APP_PASSWORD: "revoked"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "manual"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOGIN_NAME: "adam", CONF_APP_PASSWORD: "fresh"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_APP_PASSWORD] == "fresh"


async def test_options_hide_lists_and_set_label(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="adam@cloud.example.com",
        data={CONF_SERVER: SERVER, CONF_LOGIN_NAME: "adam", CONF_APP_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)
    lists = [ShoppingListInfo(4, "Weekly shop"), ShoppingListInfo(5, "Party")]

    with patch(f"{FLOW}.ShoppingListApi.async_lists", AsyncMock(return_value=lists)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_HIDDEN_LISTS: ["5"], CONF_VIA_LABEL: "Kitchen"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_HIDDEN_LISTS: [5], CONF_VIA_LABEL: "Kitchen"}


async def test_empty_label_is_kept_empty(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="adam@cloud.example.com",
        data={CONF_SERVER: SERVER, CONF_LOGIN_NAME: "adam", CONF_APP_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    with patch(f"{FLOW}.ShoppingListApi.async_lists", AsyncMock(return_value=[])):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_HIDDEN_LISTS: []})

    assert entry.options == {CONF_HIDDEN_LISTS: [], CONF_VIA_LABEL: ""}
