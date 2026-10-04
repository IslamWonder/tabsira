"""
What a browser may tell us about an error it saw.

Every bound here is a spam bound as much as a schema: the endpoint needs no
sign-in, so a report is small, a batch is short, and the server keeps the right
to drop the lot.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_ITEMS = 10
MAX_BREADCRUMBS = 20
MAX_CONTEXT_KEYS = 20

Scalar = str | int | float | bool | None

# An exception type or a breadcrumb category is a code identifier (`TypeError`, `ui.click`),
# never a person's words, so nothing else is accepted.
IDENTIFIER = r"^[A-Za-z0-9_.$-]+$"
MAX_IDENTIFIER = 100


class ClientBreadcrumb(BaseModel):
    """One thing that happened before the error, as the page remembers it."""

    category: str = Field(default="log", max_length=64, pattern=IDENTIFIER)
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str = Field(max_length=500)
    timestamp: float | None = None


class ClientReport(BaseModel):
    """One error or log record from the browser."""

    kind: Literal["error", "log"] = "error"
    level: Literal["warning", "error", "fatal"] = "error"
    message: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=MAX_IDENTIFIER, pattern=IDENTIFIER)
    stack: str | None = Field(default=None, max_length=16_000)
    url: str | None = Field(default=None, max_length=2000)
    handled: bool = True
    context: dict[str, Scalar] | None = None
    breadcrumbs: list[ClientBreadcrumb] = Field(default_factory=list, max_length=MAX_BREADCRUMBS)
    # The web build that saw it, as `git describe` named it (v1.0.0-29-gabc1234).
    release: str | None = Field(default=None, max_length=100, pattern=r"^[\w.+-]+$")

    @field_validator("context")
    @classmethod
    def _bounded_context(cls, value: dict[str, Scalar] | None) -> dict[str, Scalar] | None:
        if value is not None and len(value) > MAX_CONTEXT_KEYS:
            message = f"context may carry at most {MAX_CONTEXT_KEYS} keys"
            raise ValueError(message)
        return value


class ClientReportBatch(BaseModel):
    """A page's pending reports, flushed together."""

    items: list[ClientReport] = Field(min_length=1, max_length=MAX_ITEMS)
