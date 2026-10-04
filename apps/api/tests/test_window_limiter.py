"""The in-memory limiter: a budget per key and window, bounded in memory."""

from __future__ import annotations

from fastapi import FastAPI, Request

from src.services.window_limiter import (
    AddressLimits,
    WindowLimiter,
    limits_of,
    too_many_requests,
)


def test_a_key_may_hit_up_to_its_limit_then_is_told_how_long_to_wait(moving_clock):
    limiter = WindowLimiter(limit=3, window_seconds=60)

    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]
    moving_clock.advance(seconds=20)

    assert limiter.hit("a") == 40.0
    assert limiter.hit("a") == 40.0


def test_keys_do_not_share_a_budget(moving_clock):
    limiter = WindowLimiter(limit=1, window_seconds=60)

    assert limiter.hit("a") is None
    assert limiter.hit("a") is not None
    assert limiter.hit("b") is None


def test_the_budget_comes_back_when_the_window_ends(moving_clock):
    limiter = WindowLimiter(limit=1, window_seconds=60)
    assert limiter.hit("a") is None
    assert limiter.hit("a") is not None

    moving_clock.advance(seconds=60)

    assert limiter.hit("a") is None


def test_expired_keys_are_forgotten_before_live_ones(moving_clock):
    limiter = WindowLimiter(limit=1, window_seconds=60, max_keys=2)
    limiter.hit("old")
    moving_clock.advance(seconds=61)
    limiter.hit("live")

    limiter.hit("new")

    assert set(limiter._windows) == {"live", "new"}


def test_a_full_table_drops_the_oldest_live_key_instead_of_refusing_a_new_one(moving_clock):
    limiter = WindowLimiter(limit=1, window_seconds=60, max_keys=2)
    limiter.hit("a")
    limiter.hit("b")

    # A third address is counted, never refused for lack of room; the oldest key resets.
    assert limiter.hit("c") is None

    assert set(limiter._windows) == {"b", "c"}
    assert limiter.hit("a") is None


def test_address_limits_count_each_address_and_all_of_them(moving_clock):
    limits = AddressLimits(per_address=2, overall=3, window_seconds=60)

    assert [limits.hit("a"), limits.hit("a")] == [None, None]
    # The address is over its own budget; that call does not spend the shared one.
    assert limits.hit("a") == 60.0
    assert limits.hit("b") is None
    # Three allowed calls in all: a fourth, from a fresh address, is refused.
    assert limits.hit("c") == 60.0


def test_the_limits_of_an_application_are_built_once_under_their_name():
    application = FastAPI()
    request = Request({"type": "http", "app": application, "headers": []})
    built: list[AddressLimits] = []

    def make() -> AddressLimits:
        built.append(AddressLimits(1, 1, 1))
        return built[-1]

    first = limits_of(request, "my_limits", make)
    second = limits_of(request, "my_limits", make)

    assert first is second is application.state.my_limits
    assert len(built) == 1


def test_a_refusal_is_a_429_that_says_when_to_come_back():
    error = too_many_requests(12.4, "Slow down.")

    assert (error.status_code, error.code.value, error.detail) == (
        429,
        "RATE_LIMITED",
        "Slow down.",
    )
    assert error.headers == {"Retry-After": "12"}
    # Never less than a second, so a client cannot be told to retry at once.
    assert too_many_requests(0.0, "x").headers == {"Retry-After": "1"}
