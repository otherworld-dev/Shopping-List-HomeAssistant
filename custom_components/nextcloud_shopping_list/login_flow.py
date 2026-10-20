"""Nextcloud's Login Flow v2.

Home Assistant opens Nextcloud's own grant-access page, the user approves
it, and Nextcloud hands out an app password named after our user agent,
which the user can revoke from their security settings. Their real password
never reaches Home Assistant.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import aiohttp

from .api import TIMEOUT, ApiConnectionError, ApiError
from .const import USER_AGENT


@dataclass(frozen=True, slots=True)
class LoginStart:
    """Where to send the user, and where to ask whether they have approved it."""

    login_url: str
    poll_endpoint: str
    token: str


@dataclass(frozen=True, slots=True)
class Credentials:
    """What Nextcloud hands back once access is granted."""

    server: str
    login_name: str
    app_password: str


async def async_start(session: aiohttp.ClientSession, server: str) -> LoginStart:
    try:
        async with session.post(
            f"{server.rstrip('/')}/index.php/login/v2", headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
        ) as resp:
            if resp.status != 200:
                raise ApiError(f"Nextcloud answered {resp.status}")
            data = await resp.json(content_type=None)
    except ApiError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        raise ApiConnectionError(str(err) or type(err).__name__) from err
    try:
        return LoginStart(login_url=data["login"], poll_endpoint=data["poll"]["endpoint"], token=data["poll"]["token"])
    except (KeyError, TypeError) as err:
        raise ApiError("This does not look like a Nextcloud server") from err


async def async_poll(session: aiohttp.ClientSession, start: LoginStart) -> Credentials | None:
    """The app password once the user has granted access, None while they haven't yet."""
    try:
        async with session.post(start.poll_endpoint, data={"token": start.token}, timeout=TIMEOUT) as resp:
            if resp.status == 404:
                return None
            if resp.status != 200:
                raise ApiError(f"Nextcloud answered {resp.status}")
            data = await resp.json(content_type=None)
    except ApiError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        raise ApiConnectionError(str(err) or type(err).__name__) from err
    return Credentials(server=data["server"], login_name=data["loginName"], app_password=data["appPassword"])
