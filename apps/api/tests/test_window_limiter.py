"""The in-memory limiter: a budget per key and window, bounded in memory."""

from __future__ import annotations

from src.services.window_limiter import WindowLimiter


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
