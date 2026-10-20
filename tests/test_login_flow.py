"""Nextcloud's Login Flow v2: the grant-access page that hands out an app password."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nextcloud_shopping_list import login_flow

from .conftest import SERVER

POLL = SERVER + "/index.php/login/v2/poll"
LOGIN = SERVER + "/index.php/login/v2/flow/abc"


async def test_start_returns_login_url_and_poll(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{SERVER}/index.php/login/v2", json={"poll": {"token": "tok", "endpoint": POLL}, "login": LOGIN})

    start = await login_flow.async_start(async_get_clientsession(hass), SERVER)

    assert start == login_flow.LoginStart(login_url=LOGIN, poll_endpoint=POLL, token="tok")
    # Nextcloud names the app password after the user agent
    assert aioclient_mock.mock_calls[-1][3]["User-Agent"] == "Home Assistant Shopping List"


async def test_poll_pending_is_none(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(POLL, status=404, json=[])
    start = login_flow.LoginStart(login_url=LOGIN, poll_endpoint=POLL, token="tok")

    assert await login_flow.async_poll(async_get_clientsession(hass), start) is None
    assert aioclient_mock.mock_calls[-1][2] == {"token": "tok"}


async def test_poll_done_returns_credentials(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(POLL, json={"server": SERVER, "loginName": "adam", "appPassword": "secret"})
    start = login_flow.LoginStart(login_url=LOGIN, poll_endpoint=POLL, token="tok")

    creds = await login_flow.async_poll(async_get_clientsession(hass), start)

    assert creds == login_flow.Credentials(server=SERVER, login_name="adam", app_password="secret")
