"""Setting up the Nextcloud Shopping List integration."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

import probatio
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from yarl import URL

from . import login_flow
from .api import ApiAuthError, ApiError, ShoppingListApi
from .const import (
    CONF_APP_PASSWORD,
    CONF_HIDDEN_LISTS,
    CONF_LOGIN_NAME,
    CONF_SERVER,
    CONF_VIA_LABEL,
    DEFAULT_VIA_LABEL,
    DOMAIN,
    REQUIRED_FEATURES,
    REQUIRED_SERVER_VERSION,
)
from .login_flow import Credentials, LoginStart

# How often to ask Nextcloud whether access was granted, and for how long
POLL_INTERVAL = 2
LOGIN_TIMEOUT = 600

SERVER_SCHEMA = probatio.Schema({probatio.Required(CONF_SERVER): str})
MANUAL_SCHEMA = probatio.Schema({probatio.Required(CONF_LOGIN_NAME): str, probatio.Required(CONF_APP_PASSWORD): str})


def normalise_server(raw: str) -> str:
    """A bare host is taken as https, with no trailing slash."""
    server = raw.strip().rstrip("/")
    return server if "://" in server else f"https://{server}"


class NextcloudShoppingListConfigFlow(ConfigFlow, domain=DOMAIN):
    """Sign in through Nextcloud's grant-access page, or with an app password."""

    VERSION = 1

    def __init__(self) -> None:
        self._server: str | None = None
        self._start: LoginStart | None = None
        self._credentials: Credentials | None = None
        self._timed_out = False
        self._manual = False
        self._wait_task: asyncio.Task[None] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        return OptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._server = normalise_server(user_input[CONF_SERVER])
            return await self.async_step_method()
        return self.async_show_form(step_id="user", data_schema=SERVER_SCHEMA)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._server = entry_data[CONF_SERVER]
        return await self.async_step_method()

    async def async_step_method(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="method", menu_options=["auth", "manual"])

    async def async_step_auth(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Send the user to Nextcloud's grant-access page and wait for it."""
        if self._credentials is not None:
            return self.async_external_step_done(next_step_id="finish")
        if self._timed_out:
            return self.async_external_step_done(next_step_id="login_timeout")
        if self._start is None:
            try:
                self._start = await login_flow.async_start(async_get_clientsession(self.hass), self._server)
            except ApiError:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self.add_suggested_values_to_schema(SERVER_SCHEMA, {CONF_SERVER: self._server}),
                    errors={"base": "cannot_connect"},
                )
            # Not eager: the wait must not finish before this step is even shown
            self._wait_task = self.hass.async_create_background_task(
                self._async_wait_for_login(), f"{DOMAIN} login", eager_start=False
            )
        return self.async_external_step(step_id="auth", url=self._start.login_url)

    async def _async_wait_for_login(self) -> None:
        session = async_get_clientsession(self.hass)
        deadline = time.monotonic() + LOGIN_TIMEOUT
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                credentials = await login_flow.async_poll(session, self._start)
            except ApiError:
                credentials = None
            if credentials is not None:
                self._credentials = credentials
                break
        else:
            self._timed_out = True
        with suppress(UnknownFlow):
            await self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)

    @callback
    def async_remove(self) -> None:
        """Stop waiting for access when the dialog is closed."""
        if self._wait_task is not None:
            self._wait_task.cancel()

    async def async_step_login_timeout(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason="login_timeout")

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A login name and an app password typed in by hand."""
        self._manual = True
        if user_input is not None:
            self._credentials = Credentials(
                server=self._server,
                login_name=user_input[CONF_LOGIN_NAME].strip(),
                app_password=user_input[CONF_APP_PASSWORD].strip(),
            )
            return await self.async_step_finish()
        return self.async_show_form(step_id="manual", data_schema=MANUAL_SCHEMA)

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Check the server has what this needs, then save the entry."""
        creds = self._credentials
        api = ShoppingListApi(
            async_get_clientsession(self.hass), creds.server, creds.login_name, creds.app_password, None
        )
        try:
            version, features = await api.async_features()
        except ApiAuthError:
            return self._fail("invalid_auth")
        except ApiError:
            return self._fail("cannot_connect")
        if version is None:
            return self.async_abort(reason="missing_app")
        if any(feature not in features for feature in REQUIRED_FEATURES):
            return self.async_abort(reason="server_too_old", description_placeholders={"version": REQUIRED_SERVER_VERSION})

        host = URL(creds.server).host or creds.server
        await self.async_set_unique_id(f"{creds.login_name}@{host}".lower())
        data = {CONF_SERVER: creds.server, CONF_LOGIN_NAME: creds.login_name, CONF_APP_PASSWORD: creds.app_password}
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"{creds.login_name} on {host}", data=data)

    def _fail(self, error: str) -> ConfigFlowResult:
        """Typed-in details can be corrected; a grant-access login starts again."""
        if self._manual:
            return self.async_show_form(step_id="manual", data_schema=MANUAL_SCHEMA, errors={"base": error})
        return self.async_abort(reason=error)


class OptionsFlowHandler(OptionsFlowWithReload):
    """Which lists to show, and the label changes are made under."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        if user_input is not None:
            return self.async_create_entry(
                data={
                    # Hidden rather than shown, so lists made later appear by themselves
                    CONF_HIDDEN_LISTS: [int(list_id) for list_id in user_input.get(CONF_HIDDEN_LISTS, [])],
                    # Cleared means no label, so the account's own name shows
                    CONF_VIA_LABEL: (user_input.get(CONF_VIA_LABEL) or "").strip(),
                }
            )

        api = ShoppingListApi(
            async_get_clientsession(self.hass),
            entry.data[CONF_SERVER],
            entry.data[CONF_LOGIN_NAME],
            entry.data[CONF_APP_PASSWORD],
            None,
        )
        try:
            lists = await api.async_lists()
        except ApiError:
            return self.async_abort(reason="cannot_connect")

        # Only lists that still exist: a deleted one can't be shown, so it could never be unticked
        existing = {info.id for info in lists}
        hidden = [str(list_id) for list_id in entry.options.get(CONF_HIDDEN_LISTS, []) if list_id in existing]
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_HIDDEN_LISTS, default=hidden): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=str(info.id), label=info.title) for info in lists],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                probatio.Optional(
                    CONF_VIA_LABEL,
                    description={"suggested_value": entry.options.get(CONF_VIA_LABEL, DEFAULT_VIA_LABEL)},
                ): TextSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
