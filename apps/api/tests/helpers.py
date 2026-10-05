"""Small helpers shared by test modules."""

from __future__ import annotations

import secrets
from collections.abc import Iterable

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.features import FeatureFlag


def client_for(application: FastAPI, base_url: str = "http://test") -> AsyncClient:
    """An HTTP client wired straight to `application`; a server crash is a 500, not an exception."""
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url=base_url)


def any_id() -> int:
    """Return a public id nobody holds: a positive 62-bit number."""
    return secrets.randbelow(2**62) + 1


def switched[S: Settings](
    settings: S, *, off: Iterable[FeatureFlag] = (), on: Iterable[FeatureFlag] = ()
) -> S:
    """Return a copy of `settings` with features named off or on, added to what it already names."""

    def merged(current: str, more: Iterable[FeatureFlag]) -> str:
        return ",".join([*(name for name in current.split(",") if name), *(f.value for f in more)])

    return settings.model_copy(
        update={
            "disabled_features": merged(settings.disabled_features, off),
            "enabled_features": merged(settings.enabled_features, on),
        }
    )
