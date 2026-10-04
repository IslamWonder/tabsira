"""
Rate limits of every write on the social network.

Each kind of write has a budget per account and a budget over all accounts, counted by the
shared in-memory limiter (`window_limiter`) of the worker that serves the request. The
numbers are a bound on spam and on a runaway client, not a quota: a person reading and
reacting at human speed never meets them, and with N workers the real ceiling is N times
higher. The key is the account, never an address: every write needs a signed-in account.
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import Request

from src.services.window_limiter import AddressLimits


class WriteKind(StrEnum):
    IDENTITY = "identity"  # the handle and the public name
    POST = "post"  # a draft, its edits, its submission, its withdrawal
    COMMENT = "comment"  # a comment, a reply, a deletion
    REACTION = "reaction"  # a like, a bookmark, a follow
    REPORT = "report"
    BLOCK = "block"


# (writes per account, writes over all accounts, window in seconds)
LIMITS: dict[WriteKind, tuple[int, int, float]] = {
    WriteKind.IDENTITY: (5, 500, 3600),
    WriteKind.POST: (20, 5000, 3600),
    WriteKind.COMMENT: (15, 3000, 600),
    WriteKind.REACTION: (120, 30000, 60),
    WriteKind.REPORT: (10, 1000, 3600),
    WriteKind.BLOCK: (30, 3000, 3600),
}


class SocialLimits:
    """One `AddressLimits` per kind of write, from `LIMITS`; a test may replace some kinds."""

    def __init__(self, table: dict[WriteKind, tuple[int, int, float]] | None = None) -> None:
        self._limits = {
            kind: AddressLimits(*numbers) for kind, numbers in {**LIMITS, **(table or {})}.items()
        }

    def hit(self, kind: WriteKind, account: str) -> float | None:
        """Count one write; None when allowed, else the seconds to wait."""
        return self._limits[kind].hit(account)


def get_social_limits(request: Request) -> SocialLimits:
    """Return the application's limits, built on first use."""
    limits: SocialLimits | None = getattr(request.app.state, "social_limits", None)
    if limits is None:
        limits = SocialLimits()
        request.app.state.social_limits = limits
    return limits
