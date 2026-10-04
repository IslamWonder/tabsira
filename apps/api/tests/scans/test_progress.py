"""Progress events on Redis, their replay, the live stream, and the temporary photo store."""

from __future__ import annotations

import asyncio

from src.pipeline.schemas import EncodedImage
from src.scans import buffer, progress
from src.scans.progress import ProgressEvent


async def collect(redis, scan_id, **values) -> list[ProgressEvent]:
    defaults = {"run": 1, "after": 0, "fallback": None, "max_seconds": 0.3}
    return [event async for event in progress.stream(redis, scan_id, **(defaults | values))]


async def test_events_are_numbered_kept_for_replay_and_expire(redis):
    scan_id = 7_314_159_265_358_979_323

    first = await progress.publish(redis, scan_id, "queued", {"run": 1}, ttl=60)
    second = await progress.publish(redis, scan_id, "stage", {"run": 1, "stage": "x"}, ttl=60)

    assert (first.id, second.id) == (1, 2)
    assert [event.id for event in await progress.replay(redis, scan_id)] == [1, 2]
    assert await progress.replay(redis, scan_id, after=1) == [second]
    assert 0 < await redis.ttl(progress.events_key(scan_id)) <= 60
    assert 0 < await redis.ttl(progress.sequence_key(scan_id)) <= 60


async def test_the_replay_keeps_only_the_latest_events(redis):
    scan_id = 7_314_159_265_358_979_323
    for _ in range(progress.MAX_EVENTS + 5):
        await progress.publish(redis, scan_id, "stage", {"run": 1}, ttl=60)

    kept = await progress.replay(redis, scan_id)

    assert len(kept) == progress.MAX_EVENTS
    assert kept[0].id == 6


def test_an_event_speaks_server_sent_events():
    event = ProgressEvent(id=3, event="done", data={"run": 2, "outcome": "insights"})

    assert event.terminal
    assert event.run == 2
    assert ProgressEvent(id=1, event="queued", data={"run": "x"}).run == 0
    assert event.as_sse() == {
        "id": "3",
        "event": "done",
        "data": '{"run":2,"outcome":"insights"}',
    }


def test_a_last_event_id_is_a_small_number_or_nothing():
    assert progress.parse_last_event_id(None) == 0
    assert progress.parse_last_event_id(" 12 ") == 12
    for bad in ("", "abc", "-3", "9" * 19):
        assert progress.parse_last_event_id(bad) == 0


async def test_a_stream_replays_what_was_missed_and_ends_at_the_terminal_event(redis):
    scan_id = 7_314_159_265_358_979_323
    await progress.publish(redis, scan_id, "queued", {"run": 1}, ttl=60)
    await progress.publish(redis, scan_id, "stage", {"run": 1}, ttl=60)
    await progress.publish(redis, scan_id, "done", {"run": 1}, ttl=60)
    await progress.publish(redis, scan_id, "stage", {"run": 1}, ttl=60)

    assert [event.id for event in await collect(redis, scan_id)] == [1, 2, 3]
    assert [event.id for event in await collect(redis, scan_id, after=2)] == [3]


async def test_a_stream_skips_an_earlier_run(redis):
    scan_id = 7_314_159_265_358_979_323
    await progress.publish(redis, scan_id, "done", {"run": 1}, ttl=60)
    await progress.publish(redis, scan_id, "queued", {"run": 2}, ttl=60)
    await progress.publish(redis, scan_id, "failed", {"run": 2, "code": "X"}, ttl=60)

    assert [event.event for event in await collect(redis, scan_id, run=2)] == ["queued", "failed"]


async def test_a_finished_run_whose_events_expired_answers_from_the_database(redis):
    fallback = ProgressEvent(id=0, event="done", data={"run": 1})

    assert await collect(redis, 7_314_159_265_358_979_323, fallback=fallback) == [fallback]


async def test_a_stream_hears_live_events_once_and_stops_at_the_end(redis):
    scan_id = 7_314_159_265_358_979_323
    await progress.publish(redis, scan_id, "queued", {"run": 2}, ttl=60)

    async def later() -> None:
        await asyncio.sleep(0.05)
        await progress.publish(redis, scan_id, "stage", {"run": 1}, ttl=60)
        await progress.publish(redis, scan_id, "stage", {"run": 2, "stage": "searching"}, ttl=60)
        await progress.publish(redis, scan_id, "done", {"run": 2}, ttl=60)

    task = asyncio.create_task(later())
    events = await collect(redis, scan_id, run=2, max_seconds=5)
    await task

    assert [event.event for event in events] == ["queued", "stage", "done"]
    assert [event.id for event in events] == [1, 3, 4]


async def test_a_live_event_already_replayed_is_not_sent_again(redis):
    scan_id = 7_314_159_265_358_979_323
    stream = progress.stream(
        redis, scan_id, run=1, after=0, fallback=None, max_seconds=5
    ).__aiter__()
    await progress.publish(redis, scan_id, "queued", {"run": 1}, ttl=60)
    first = await anext(stream)
    # The same payload again on the channel, as a reader joining between the two reads sees it.
    await redis.publish(progress.channel(scan_id), first.model_dump_json())
    await progress.publish(redis, scan_id, "failed", {"run": 1}, ttl=60)

    assert [first.id, (await anext(stream)).id] == [1, 2]
    await stream.aclose()


async def test_a_stream_without_news_ends_after_its_life(redis):
    ticks = iter([0.0, 0.0, 10.0])

    events = [
        event
        async for event in progress.stream(
            redis,
            7_314_159_265_358_979_323,
            run=1,
            after=0,
            fallback=None,
            max_seconds=5,
            clock=lambda: next(ticks),
        )
    ]

    assert events == []


async def test_the_photo_is_kept_sealed_for_its_time_and_dropped_on_demand(
    redis, flow_settings, make_settings
):
    scan_id = 7_314_159_265_358_979_323
    key = buffer.photo_key(flow_settings)
    full = EncodedImage(data=b"full photo bytes", width=4, height=4)
    small = EncodedImage(data=b"small", width=2, height=2)

    await buffer.put(redis, scan_id, full=full, model=small, ttl=120, key=key)

    stored = await redis.get(f"scan:{scan_id}:image")
    assert b"full photo bytes" not in stored
    assert await buffer.get(redis, scan_id, buffer.Copy.FULL, key=key) == b"full photo bytes"
    assert await buffer.get(redis, scan_id, buffer.Copy.MODEL, key=key) == b"small"
    assert 0 < await redis.ttl(f"scan:{scan_id}:image") <= 120
    # Another server key, or a sealed value moved to another scan or copy, opens nothing.
    other = buffer.photo_key(make_settings(hash_secret="x" * 40))
    assert other != key
    assert await buffer.get(redis, scan_id, buffer.Copy.FULL, key=other) is None
    await redis.set(f"scan:{scan_id}:model_image", stored)
    assert await buffer.get(redis, scan_id, buffer.Copy.MODEL, key=key) is None
    await buffer.drop(redis, scan_id, buffer.Copy.MODEL)
    assert not await buffer.kept(redis, scan_id, buffer.Copy.MODEL)
    assert await buffer.get(redis, scan_id, buffer.Copy.MODEL, key=key) is None
    assert await buffer.kept(redis, scan_id, buffer.Copy.FULL)
    await buffer.drop(redis, scan_id)
    assert await buffer.get(redis, scan_id, buffer.Copy.FULL, key=key) is None
