"""Client for the Shopping List app's OCS API."""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import aiohttp

from .const import API_BASE, CAPABILITIES_PATH, VIA_HEADER
from .models import Area, Item, ShoppingListInfo

TIMEOUT = aiohttp.ClientTimeout(total=20)


class ApiError(Exception):
    """The server answered with an error."""


class ApiAuthError(ApiError):
    """Nextcloud refused the login name and app password."""


class ApiConnectionError(ApiError):
    """Nextcloud could not be reached."""


class ApiRefused(ApiError):
    """The app refused the request, for example an amount it could not read."""


class ShoppingListApi:
    """Talks to one Nextcloud account's Shopping List app."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        server: str,
        login_name: str,
        app_password: str,
        via_label: str | None,
    ) -> None:
        self._session = session
        self._server = server.rstrip("/")
        token = base64.b64encode(f"{login_name}:{app_password}".encode()).decode()
        self._headers = {
            "OCS-APIRequest": "true",
            "Accept": "application/json",
            "Authorization": f"Basic {token}",
        }
        # Sent with every change, so the list shows "Home Assistant" against it
        self._via = via_label or None

    async def _request(self, method: str, path: str, *, body: dict[str, Any] | None = None, write: bool = False) -> Any:
        headers = dict(self._headers)
        if write and self._via:
            headers[VIA_HEADER] = self._via
        try:
            async with self._session.request(
                method, f"{self._server}{path}", json=body, headers=headers, timeout=TIMEOUT
            ) as resp:
                if resp.status == 401:
                    raise ApiAuthError("Nextcloud refused the app password")
                if resp.status == 204:
                    return None
                try:
                    payload = await resp.json(content_type=None)
                except ValueError:
                    payload = None
                data = payload.get("ocs", {}).get("data") if isinstance(payload, dict) else None
                if resp.status >= 400:
                    message = data.get("message") if isinstance(data, dict) else None
                    if resp.status in (400, 403, 404):
                        raise ApiRefused(message or f"Nextcloud answered {resp.status}")
                    raise ApiError(message or f"Nextcloud answered {resp.status}")
                return data
        except ApiError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ApiConnectionError(str(err) or type(err).__name__) from err

    async def async_features(self) -> tuple[str | None, list[str]]:
        """The app's version and features, or (None, []) when it isn't installed."""
        data = await self._request("GET", CAPABILITIES_PATH)
        app = (data or {}).get("capabilities", {}).get("shopping_list") if isinstance(data, dict) else None
        if not isinstance(app, dict):
            return None, []
        return app.get("version"), list(app.get("features") or [])

    async def async_lists(self) -> list[ShoppingListInfo]:
        return [ShoppingListInfo.from_json(d) for d in await self._request("GET", f"{API_BASE}/lists") or []]

    async def async_items(self, list_id: int) -> list[Item]:
        return [Item.from_json(d) for d in await self._request("GET", f"{API_BASE}/lists/{list_id}/items") or []]

    async def async_areas(self, list_id: int) -> list[Area]:
        return [Area.from_json(d) for d in await self._request("GET", f"{API_BASE}/lists/{list_id}/areas") or []]

    async def async_add_text(self, list_id: int, text: str) -> Item:
        """Add a line as it was said or typed; the server reads, merges and files it."""
        data = await self._request("POST", f"{API_BASE}/lists/{list_id}/items", body={"text": text}, write=True)
        return Item.from_json(data)

    async def async_update_text(self, list_id: int, item_id: int, text: str) -> Item:
        data = await self._request("PUT", f"{API_BASE}/lists/{list_id}/items/{item_id}", body={"text": text}, write=True)
        return Item.from_json(data)

    async def async_update_amount(self, list_id: int, item_id: int, amount_text: str) -> Item:
        """Change only the amount; the server refuses anything that isn't one."""
        data = await self._request(
            "PUT", f"{API_BASE}/lists/{list_id}/items/{item_id}", body={"amountText": amount_text}, write=True
        )
        return Item.from_json(data)

    async def async_check(self, list_id: int, item_id: int, checked: bool) -> Item:
        data = await self._request(
            "PUT", f"{API_BASE}/lists/{list_id}/items/{item_id}/check", body={"checked": checked}, write=True
        )
        return Item.from_json(data)

    async def async_delete(self, list_id: int, item_id: int) -> None:
        await self._request("DELETE", f"{API_BASE}/lists/{list_id}/items/{item_id}", write=True)

    async def async_clear_checked(self, list_id: int) -> None:
        await self._request("DELETE", f"{API_BASE}/lists/{list_id}/items/checked", write=True)

    async def async_reorder(self, list_id: int, item_ids: list[int]) -> None:
        await self._request(
            "POST", f"{API_BASE}/lists/{list_id}/items/reorder", body={"sortedIds": item_ids}, write=True
        )
