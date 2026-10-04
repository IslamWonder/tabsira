"""
A rate limiter that lives in this process's memory.

For the routes that must keep working, and stay cheap, exactly when the database
is struggling: the browser error report is posted when something has already
broken, and a limiter that wrote a row per call would add to the damage. The
sign-in limits stay in PostgreSQL (`rate_limit`), where every worker shares them.

Each worker counts on its own, so with N workers the effective budget is N times
the limit. That is a spam bound, not a quota: the numbers are chosen with it in
mind. Fixed windows keep the memory per key constant; a caller can use up to
twice its limit across a window boundary.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from src import clock
from src.errors import AppError, ErrorCode


@dataclass
class _Window:
    started: float
    count: int


class WindowLimiter:
    """Allow `limit` hits per `window_seconds` for each key."""

    def __init__(self, limit: int, window_seconds: float, *, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._windows: OrderedDict[str, _Window] = OrderedDict()

    def hit(self, key: str) -> float | None:
        """
        Count one call for `key`.

        Returns None when it is allowed, or the seconds until the window ends when
        the key has used up its budget.
        """
        now = clock.monotonic()
        window = self._windows.get(key)
        if window is None or now - window.started >= self.window_seconds:
            window = _Window(started=now, count=0)
            self._windows[key] = window
            self._windows.move_to_end(key)
            self._make_room(now)
        window.count += 1
        if window.count > self.limit:
            return max(self.window_seconds - (now - window.started), 0.0)
        return None

    def _make_room(self, now: float) -> None:
        """
        Forget what is no longer counted, then the oldest keys, to stay under `max_keys`.

        Forgetting a live key resets its count: the limiter fails open on
        capacity, so a flood of fresh addresses can never lock a real visitor out.
        """
        if len(self._windows) <= self.max_keys:
            return
        expired = [k for k, w in self._windows.items() if now - w.started >= self.window_seconds]
        for key in expired:
            del self._windows[key]
        while len(self._windows) > self.max_keys:
            self._windows.popitem(last=False)


class AddressLimits:
    """
    The two limits of a route that anyone may call: one per address, one over all of them.

    The second stops a flood of fresh addresses that no single-address budget would.
    """

    def __init__(self, per_address: int, overall: int, window_seconds: float) -> None:
        self.per_address = WindowLimiter(per_address, window_seconds)
        self.overall = WindowLimiter(overall, window_seconds, max_keys=1)

    def hit(self, address_hash: str) -> float | None:
        """Count one call; None when allowed, else the seconds to wait."""
        retry_after = self.per_address.hit(address_hash)
        if retry_after is None:
            retry_after = self.overall.hit("all")
        return retry_after


def limits_of(request: Request, name: str, make: Callable[[], AddressLimits]) -> AddressLimits:
    """Return the application's limits called `name`, built with `make` on first use."""
    state = request.app.state
    limits: AddressLimits | None = getattr(state, name, None)
    if limits is None:
        limits = make()
        setattr(state, name, limits)
    return limits


def too_many_requests(retry_after: float, detail: str) -> AppError:
    """Build the 429 a route raises when `AddressLimits.hit` says wait."""
    return AppError(
        ErrorCode.RATE_LIMITED,
        detail,
        status_code=429,
        headers={"Retry-After": str(max(int(retry_after), 1))},
    )
