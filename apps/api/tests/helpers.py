"""Small helpers shared by test modules."""

from __future__ import annotations

import secrets

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def client_for(application: FastAPI, base_url: str = "http://test") -> AsyncClient:
    """An HTTP client wired straight to `application`; a server crash is a 500, not an exception."""
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url=base_url)


def any_id() -> int:
    """Return a public id nobody holds: a positive 62-bit number."""
    return secrets.randbelow(2**62) + 1
