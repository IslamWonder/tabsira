"""Fixtures of the social network tests: members with their own browsers, and the scripture they cite."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.models import User
from tests.conftest import PASSPHRASE, browser_for


@dataclass
class Member:
    """An account and the browser it is signed in with."""

    user: User
    http: AsyncClient
    handle: str | None

    @property
    def id(self) -> str:
        return str(self.user.id)


MakeMember = Callable[..., Awaitable[Member]]


@pytest.fixture
async def make_member(
    make_user: Callable[..., Any], account_app: FastAPI
) -> AsyncIterator[MakeMember]:
    """
    Create accounts with a public identity, each signed in through a browser of its own.

    `identity=False` makes an account with no handle yet, `verified=False` one whose address
    nobody has proven, and `signed_in=False` returns a browser with no session.
    """
    browsers: list[AsyncClient] = []

    async def create(
        handle: str | None = "reader",
        *,
        verified: bool = True,
        identity: bool = True,
        signed_in: bool = True,
        **columns: Any,
    ) -> Member:
        email = f"{handle or 'member'}@example.com"
        if identity and handle is not None:
            columns = {"handle": handle, "public_name": f"{handle} name", **columns}
        user = await make_user(email, verified=verified, **columns)
        browser = browser_for(account_app)
        browsers.append(browser)
        if signed_in:
            response = await browser.post(
                "/auth/login", json={"email": email, "password": PASSPHRASE}
            )
            assert response.status_code == 200, response.text
        return Member(user, browser, handle)

    yield create
    for browser in browsers:
        await browser.aclose()
