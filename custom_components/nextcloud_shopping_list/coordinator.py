"""Keeps the shown lists, their shop areas and items fresh."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiAuthError, ApiError, ApiRefused, ShoppingListApi
from .const import CONF_HIDDEN_LISTS, DOMAIN, SCAN_INTERVAL
from .models import Area, Item, ShoppingListInfo

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ListData:
    """One list as it is now."""

    info: ShoppingListInfo
    areas: list[Area]
    items: list[Item]


@dataclass(frozen=True, slots=True)
class ShoppingData:
    """Every shown list, by id."""

    lists: dict[int, ListData]


@dataclass(slots=True)
class RuntimeData:
    api: ShoppingListApi
    coordinator: ShoppingListCoordinator


type ShoppingListConfigEntry = ConfigEntry[RuntimeData]


class ShoppingListCoordinator(DataUpdateCoordinator[ShoppingData]):
    """Polls the lists the options don't hide."""

    config_entry: ShoppingListConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ShoppingListConfigEntry, api: ShoppingListApi) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.api = api
        self._hidden = set(entry.options.get(CONF_HIDDEN_LISTS, []))

    async def _async_update_data(self) -> ShoppingData:
        try:
            lists = await self.api.async_lists()
            shown = [info for info in lists if info.id not in self._hidden]
            fetched = await asyncio.gather(*(self._async_fetch(info) for info in shown))
        except ApiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ApiError as err:
            raise UpdateFailed(str(err)) from err
        return ShoppingData(lists={data.info.id: data for data in fetched if data is not None})

    async def _async_fetch(self, info: ShoppingListInfo) -> ListData | None:
        try:
            items, areas = await asyncio.gather(self.api.async_items(info.id), self.api.async_areas(info.id))
        except ApiRefused:
            # Deleted or unshared since the lists were read; gone at the next refresh anyway
            return None
        return ListData(info=info, areas=sorted(areas, key=lambda area: area.sort_order), items=items)
