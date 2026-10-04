"""Small helpers shared by test modules."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def client_for(application: FastAPI) -> AsyncClient:
    """An HTTP client wired straight to `application`; a server crash is a 500, not an exception."""
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")
