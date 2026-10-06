"""Views of a post: counted by the page's beacon only, once per viewer a day, never the author's or a bot's."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select

from src.models import Post
from src.routers.posts import ViewLimits
from src.services import auth_service, view_service
from tests.conftest import API_HOST, BROWSER_ORIGIN, PASSPHRASE
from tests.support_social import publish_post

BROWSER = "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/141.0 Mobile Safari/537.36"
ELSEWHERE = ("203.0.113.7", 50000)


@pytest.fixture
async def redis(account_app: FastAPI) -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    account_app.state.redis = client
    yield client
    await client.aclose()


@pytest.fixture
async def stranger(account_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A guest browsing from an address no account here used."""
    async with AsyncClient(
        transport=ASGITransport(app=account_app, client=ELSEWHERE, raise_app_exceptions=False),
        base_url=API_HOST,
        headers={"Origin": BROWSER_ORIGIN, "User-Agent": BROWSER},
    ) as http:
        yield http


async def view(http: AsyncClient, post_id: str, user_agent: str | None = BROWSER) -> int:
    headers = {"User-Agent": user_agent} if user_agent is not None else {}
    if user_agent is None:
        # httpx sends its own user agent unless told otherwise.
        http.headers.pop("User-Agent", None)
    response = await http.post(f"/posts/{post_id}/view", headers=headers)
    return response.status_code


async def views(http: AsyncClient, post_id: str) -> int:
    count: int = (await http.get(f"/posts/{post_id}")).json()["views_count"]
    return count


async def keys(redis: FakeAsyncRedis) -> list[str]:
    return [key.decode() async for key in redis.scan_iter()]


async def test_a_reader_counts_once_a_day_and_reading_alone_counts_nothing(
    make_member, make_insight, guard, redis, account_settings
):
    author = await make_member("author")
    reader = await make_member("reader")
    other = await make_member("other")
    post_id = await publish_post(author, make_insight)

    assert await views(reader.http, post_id) == 0
    assert await view(reader.http, post_id) == 204
    assert await view(reader.http, post_id) == 204
    assert await views(reader.http, post_id) == 1
    # Another account on the same address is still the same address: counted once.
    assert await view(other.http, post_id) == 204
    assert await views(author.http, post_id) == 1
    key = view_service.marker(account_settings.hash_key, int(post_id), f"user:{reader.user.id}")
    assert 0 < await redis.ttl(key) <= 24 * 3600
    # A key names neither the post nor the account: nobody reading Redis learns who saw what.
    assert all(post_id not in k and str(reader.user.id) not in k for k in await keys(redis))


async def test_a_guest_counts_by_address_and_signing_in_does_not_count_twice(
    make_member, make_insight, guard, redis, stranger, account_settings
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)

    assert await view(stranger, post_id) == 204
    assert await view(stranger, post_id) == 204
    assert await views(stranger, post_id) == 1
    # Neither the address nor the hash the sessions keep of it: nothing to join with.
    session_hash = auth_service.hash_ip(account_settings, ELSEWHERE[0])
    assert all("203.0.113.7" not in k and session_hash not in k for k in await keys(redis))

    # The guest signs in on the same browser: a new account, but an address already seen.
    signed_in = await stranger.post(
        "/auth/login", json={"email": "reader@example.com", "password": PASSPHRASE}
    )
    assert signed_in.status_code == 200
    assert await view(stranger, post_id) == 204
    assert await views(stranger, post_id) == 1
    # A post this account had not seen counts, under the account and the address.
    second = await publish_post(author, make_insight)
    assert await view(stranger, second) == 204
    assert await view(reader.http, second) == 204
    assert await views(stranger, second) == 1


async def test_the_author_never_counts_and_whose_address_it_is_is_never_asked(
    make_member, make_insight, guard, redis, web
):
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)
    web.headers["User-Agent"] = BROWSER

    # A guest on an address the author's session used counts like anyone: the count must not
    # tell a neighbour on the same network who wrote the post.
    assert await view(web, post_id) == 204
    assert await views(author.http, post_id) == 1

    second = await publish_post(author, make_insight)
    assert await view(author.http, second) == 204
    # The author's own opening marked their address: signed out there the same day, still them.
    assert await view(web, second) == 204
    assert await views(author.http, second) == 0


@pytest.mark.parametrize(
    "user_agent",
    [
        None,
        "",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "facebookexternalhit/1.1",
        "WhatsApp/2.24.1 A",
        "TelegramBot (like TwitterBot)",
        "python-httpx/0.28.1",
        "curl/8.5.0",
        "Mozilla/5.0 HeadlessChrome/141.0",
    ],
)
async def test_bots_and_scripts_never_count(
    make_member, make_insight, guard, redis, stranger, user_agent
):
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)

    assert await view(stranger, post_id, user_agent) == 204
    stranger.headers["User-Agent"] = BROWSER
    assert await views(stranger, post_id) == 0


async def test_a_post_the_caller_may_not_read_answers_as_reading_does_and_counts_nothing(
    make_member, make_insight, guard, redis, stranger, db_session
):
    author = await make_member("author")
    draft = (
        await author.http.post("/posts", json={"insight_id": str(make_insight(author).insight_id)})
    ).json()["id"]

    assert await view(stranger, draft) == 404
    assert await view(stranger, "999999999") == 404
    assert await db_session.scalar(select(Post.views_count).where(Post.id == int(draft))) == 0
    assert [key async for key in redis.scan_iter()] == []


async def test_a_view_is_not_an_edit(make_member, make_insight, guard, redis, stranger, db_session):
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)
    before = await db_session.scalar(select(Post.updated_at).where(Post.id == int(post_id)))

    assert await view(stranger, post_id) == 204

    row = (
        await db_session.execute(
            select(Post.views_count, Post.updated_at)
            .where(Post.id == int(post_id))
            .execution_options(populate_existing=True)
        )
    ).one()
    assert (row.views_count, row.updated_at) == (1, before)


async def test_nothing_counts_while_redis_is_down(
    make_member, make_insight, guard, stranger, account_app
):
    class Down(FakeAsyncRedis):
        def pipeline(self, *args, **kwargs):
            raise RedisConnectionError("down")

        async def set(self, *args, **kwargs):
            raise RedisConnectionError("down")

    account_app.state.redis = Down()
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)

    assert await view(stranger, post_id) == 204
    assert await view(author.http, post_id) == 204
    assert await views(stranger, post_id) == 0


async def test_a_twin_request_that_marks_the_viewer_first_wins(
    make_member, make_insight, guard, stranger, account_app
):
    class Racing(FakeAsyncRedis):
        """Another request sets the keys between this one's check and its write."""

        def pipeline(self, *args, **kwargs):
            pipe = super().pipeline(*args, **kwargs)
            check = pipe.mget

            async def raced(names):
                seen = await check(names)
                for name in names:
                    await self.set(name, "1")
                return seen

            pipe.mget = raced
            return pipe

    account_app.state.redis = Racing()
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)

    assert await view(stranger, post_id) == 204
    assert await views(stranger, post_id) == 0


def browser_at(application: FastAPI, host: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=application, client=(host, 1), raise_app_exceptions=False),
        base_url=API_HOST,
        headers={"Origin": BROWSER_ORIGIN, "User-Agent": BROWSER},
    )


async def test_an_address_past_its_budget_is_refused_before_anything_is_looked_up(
    make_member, make_insight, guard, redis, stranger, account_app
):
    account_app.state.view_limits = ViewLimits(per_address=1, per_site=100)
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)

    assert await view(stranger, post_id) == 204
    # Not even the post is looked up: an id that does not exist answers 429, not 404.
    refused = await stranger.post("/posts/999999999/view")
    assert refused.status_code == 429
    assert refused.headers["Retry-After"]
    assert await views(stranger, post_id) == 1


async def test_a_site_rotating_its_addresses_meets_the_site_budget(
    make_member, make_insight, guard, redis, account_app
):
    account_app.state.view_limits = ViewLimits(per_address=100, per_site=2)
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)

    codes = []
    for subnet in range(1, 4):
        async with browser_at(account_app, f"2001:db8:1:{subnet}::5") as http:
            codes.append(await view(http, post_id))
    async with browser_at(account_app, "2001:db8:2:1::5") as elsewhere:
        codes.append(await view(elsewhere, post_id))
        assert await views(elsewhere, post_id) == 3

    assert codes == [204, 204, 429, 204]


def test_is_bot_reads_a_browser_as_a_person():
    assert view_service.is_bot(BROWSER) is False
    assert view_service.is_bot(None) is True
