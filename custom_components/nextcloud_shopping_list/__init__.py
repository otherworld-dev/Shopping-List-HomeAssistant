"""The Nextcloud Shopping List integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ShoppingListApi
from .const import CONF_APP_PASSWORD, CONF_LOGIN_NAME, CONF_SERVER, CONF_VIA_LABEL, DEFAULT_VIA_LABEL
from .coordinator import RuntimeData, ShoppingListConfigEntry, ShoppingListCoordinator

PLATFORMS: list[Platform] = [Platform.TODO]


async def async_setup_entry(hass: HomeAssistant, entry: ShoppingListConfigEntry) -> bool:
    api = ShoppingListApi(
        async_get_clientsession(hass),
        entry.data[CONF_SERVER],
        entry.data[CONF_LOGIN_NAME],
        entry.data[CONF_APP_PASSWORD],
        entry.options.get(CONF_VIA_LABEL, DEFAULT_VIA_LABEL),
    )
    coordinator = ShoppingListCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = RuntimeData(api=api, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ShoppingListConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
