"""The sitemap API: sections, pages, what is advertised, and what a provider may list."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.main import create_app
from src.services import sitemap_service
from src.services.sitemap_service import (
    PROVIDERS,
    SECTION_FLAGS,
    EmptyProvider,
    Entry,
    PageStamp,
    Section,
    StaticPage,
    StaticProvider,
)
from tests.helpers import client_for

STATIC_LASTMOD = "2026-10-04T00:00:00Z"
# The sources page was added a day after the others.
SOURCES_LASTMOD = "2026-10-05T00:00:00Z"
SECTIONS = ["static", "insights", "posts", "places", "profiles"]


class FakeProvider:
    """A feature's provider: a list of entries cut into pages of `page_size`, oldest first."""

    def __init__(self, section: Section, entries: list[Entry]) -> None:
        self.section = section
        self._entries = entries
        self.calls: list[tuple[int, int]] = []

    async def pages(self, db: Any, page_size: int) -> list[PageStamp]:
        stamps = []
        for start in range(0, len(self._entries), page_size):
            chunk = self._entries[start : start + page_size]
            dates = [e.lastmod for e in chunk if e.lastmod]
            stamps.append(PageStamp(page=start // page_size, lastmod=max(dates, default=None)))
        return stamps

    async def entries(self, db: Any, page: int, page_size: int) -> list[Entry]:
        self.calls.append((page, page_size))
        return self._entries[page * page_size : (page + 1) * page_size]


@pytest.fixture
def providers(monkeypatch: pytest.MonkeyPatch) -> dict[Section, Any]:
    """The registry, as a copy that a test may change and that is put back afterwards."""
    copy = dict(PROVIDERS)
    monkeypatch.setattr(sitemap_service, "PROVIDERS", copy)
    return copy


@pytest.fixture
def client_with(make_settings: Callable[..., Settings]):
    """Build a client of an application with some settings changed."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def build(**values: Any):
        async with client_for(create_app(make_settings(**values))) as http:
            yield http

    return build


async def paths(client: Any, section: str, page: int = 0) -> list[str]:
    response = await client.get(f"/sitemap/{section}", params={"page": page})
    assert response.status_code == 200
    return [entry["path"] for entry in response.json()]


# ─── The index ────────────────────────────────────────────────────────────────


async def test_the_index_names_every_section_and_only_the_static_one_has_pages(client, providers):
    # The posts and profiles sections list what the database holds (tests/test_social_sitemap.py);
    # here every section but the static one is left as it is before its feature lists anything.
    providers.update({s: EmptyProvider(s) for s in Section if s is not Section.STATIC})
    response = await client.get("/sitemap")

    assert response.status_code == 200
    body = response.json()
    assert body["page_size"] == 10_000
    assert list(body["sections"]) == SECTIONS
    assert body["sections"]["static"] == [{"page": 0, "lastmod": SOURCES_LASTMOD}]
    # Their features do not list anything yet, so they have no pages to crawl.
    assert {name: pages for name, pages in body["sections"].items() if name != "static"} == {
        name: [] for name in SECTIONS[1:]
    }


async def test_the_routes_need_no_session_and_set_no_cookie(client):
    for url in ("/sitemap", "/sitemap/static"):
        response = await client.get(url)
        assert response.status_code == 200
        assert "set-cookie" not in response.headers


async def test_the_answers_may_be_cached_for_a_few_minutes(client):
    for url in ("/sitemap", "/sitemap/static"):
        assert (await client.get(url)).headers["cache-control"] == "public, max-age=300"


# ─── The static section ───────────────────────────────────────────────────────


async def test_the_static_section_lists_the_five_public_pages_in_order(client):
    response = await client.get("/sitemap/static")

    assert response.status_code == 200
    assert response.json() == [
        *(
            {"path": path, "lastmod": STATIC_LASTMOD, "images": []}
            for path in ("/", "/terms", "/privacy", "/support")
        ),
        {"path": "/sources", "lastmod": SOURCES_LASTMOD, "images": []},
    ]


def test_every_static_path_is_in_the_one_url_form():
    for page in sitemap_service.STATIC_PAGES:
        assert re.fullmatch(r"/|(/[a-z0-9-]+)+", page.path), page.path
    assert len({page.path for page in sitemap_service.STATIC_PAGES}) == len(
        sitemap_service.STATIC_PAGES
    )


async def test_the_static_dates_are_constants_in_the_code_not_the_clock(client, moving_clock):
    moving_clock.advance(days=400)

    entries = (await client.get("/sitemap/static")).json()

    assert {entry["lastmod"] for entry in entries} == {STATIC_LASTMOD, SOURCES_LASTMOD}


async def test_a_smaller_page_size_cuts_the_static_pages(client_with):
    async with client_with(sitemap_page_size=2) as http:
        index = (await http.get("/sitemap")).json()
        first = await paths(http, "static", 0)
        last = await paths(http, "static", 1)
        third = await paths(http, "static", 2)
        past = await paths(http, "static", 3)

    assert index["page_size"] == 2
    assert [p["page"] for p in index["sections"]["static"]] == [0, 1, 2]
    assert first == ["/", "/terms"]
    assert last == ["/privacy", "/support"]
    assert third == ["/sources"]
    assert past == []


async def test_each_static_page_carries_the_newest_date_it_holds(db_session):
    provider = StaticProvider(
        [
            StaticPage("/a", date(2026, 1, 1)),
            StaticPage("/b", date(2026, 3, 1)),
            StaticPage("/c", date(2026, 2, 1)),
        ]
    )

    stamps = await provider.pages(db_session, 2)

    assert stamps == [
        PageStamp(page=0, lastmod=datetime(2026, 3, 1, tzinfo=UTC)),
        PageStamp(page=1, lastmod=datetime(2026, 2, 1, tzinfo=UTC)),
    ]
    assert await provider.pages(db_session, 10) == [
        PageStamp(page=0, lastmod=datetime(2026, 3, 1, tzinfo=UTC))
    ]
    assert await StaticProvider([]).pages(db_session, 10) == []


# ─── Bad requests and the sections that are off ───────────────────────────────


async def test_an_unknown_section_and_a_negative_page_are_refused(client):
    unknown = await client.get("/sitemap/journals")
    negative = await client.get("/sitemap/static?page=-1")
    text = await client.get("/sitemap/static?page=first")

    assert [r.status_code for r in (unknown, negative, text)] == [422, 422, 422]
    assert unknown.json()["error"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("section", "flag"),
    [
        ("insights", "feature_world"),
        ("posts", "feature_social"),
        ("places", "feature_atlas"),
        ("profiles", "feature_social"),
    ],
)
async def test_a_section_whose_feature_is_off_is_not_advertised_and_is_a_404(
    client_with, providers, section, flag
):
    providers[Section(section)] = FakeProvider(
        Section(section), [Entry("/x", datetime(2026, 1, 1, tzinfo=UTC))]
    )

    async with client_with(**{flag: False}) as http:
        index = (await http.get("/sitemap")).json()
        gone = await http.get(f"/sitemap/{section}")

    assert section not in index["sections"]
    assert "static" in index["sections"]
    assert gone.status_code == 404
    assert gone.json()["error"] == "NOT_FOUND"
    assert "cache-control" not in gone.headers


async def test_a_section_whose_feature_is_on_is_listed_with_its_pages(client_with, providers):
    providers[Section.PLACES] = FakeProvider(
        Section.PLACES, [Entry("/places/tunis", datetime(2026, 5, 1, tzinfo=UTC))]
    )

    async with client_with() as http:
        index = (await http.get("/sitemap")).json()

    assert index["sections"]["places"] == [{"page": 0, "lastmod": "2026-05-01T00:00:00Z"}]


def test_a_section_flag_names_a_real_setting_and_the_static_section_has_none():
    assert SECTION_FLAGS[Section.STATIC] is None
    assert set(SECTION_FLAGS) == set(Section)
    for flag in filter(None, SECTION_FLAGS.values()):
        assert flag in Settings.model_fields


def test_the_static_section_is_always_advertised(make_settings):
    off = make_settings(feature_world=False, feature_social=False, feature_atlas=False)

    assert sitemap_service.enabled_sections(off) == [Section.STATIC]
    assert sitemap_service.enabled_sections(make_settings()) == list(Section)


# ─── Providers ────────────────────────────────────────────────────────────────


async def test_a_feature_plugs_in_by_registering_its_provider(client_with, providers):
    old, new = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 6, 1, tzinfo=UTC)
    provider = FakeProvider(
        Section.POSTS,
        [
            Entry("/posts/one", old, ("https://tabsira.me/media/one.jpg",)),
            Entry("/posts/two", new),
            Entry("/posts/three", old),
        ],
    )

    sitemap_service.register(provider)

    assert providers[Section.POSTS] is provider
    async with client_with(sitemap_page_size=2) as http:
        index = (await http.get("/sitemap")).json()
        first = (await http.get("/sitemap/posts", params={"page": 0})).json()
        second = await paths(http, "posts", 1)
        beyond = await paths(http, "posts", 2)

    assert index["sections"]["posts"] == [
        {"page": 0, "lastmod": "2026-06-01T00:00:00Z"},
        {"page": 1, "lastmod": "2026-01-01T00:00:00Z"},
    ]
    assert first == [
        {
            "path": "/posts/one",
            "lastmod": "2026-01-01T00:00:00Z",
            "images": ["https://tabsira.me/media/one.jpg"],
        },
        {"path": "/posts/two", "lastmod": "2026-06-01T00:00:00Z", "images": []},
    ]
    assert (second, beyond) == (["/posts/three"], [])
    assert provider.calls == [(0, 2), (1, 2), (2, 2)]


async def test_a_registered_provider_replaces_the_one_before_it(providers):
    first, second = EmptyProvider(Section.INSIGHTS), EmptyProvider(Section.INSIGHTS)

    sitemap_service.register(first)
    sitemap_service.register(second)

    assert providers[Section.INSIGHTS] is second


async def test_the_default_providers_list_nothing_until_their_feature_exists(db_session):
    # The defaults, before any feature registers its own (the social network registers two).
    defaults = sitemap_service._default_providers()
    for section in Section:
        if section is Section.STATIC:
            continue
        provider = defaults[section]
        assert isinstance(provider, EmptyProvider)
        assert provider.section is section
        assert await provider.pages(db_session, 10_000) == []
        assert await provider.entries(db_session, 0, 10_000) == []


async def test_what_breaks_the_url_form_is_dropped_and_logged_never_listed(
    client_with, providers, caplog
):
    when = datetime(2026, 1, 1, tzinfo=UTC)
    providers[Section.INSIGHTS] = FakeProvider(
        Section.INSIGHTS,
        [
            Entry("/insights/ok", when),
            Entry("insights/relative", when),
            Entry("/insights/trailing/", when),
            Entry("/insights/query?x=1", when),
            Entry("/insights/fragment#a", when),
            Entry("/insights/with space", when),
            Entry("/insights/عربي", when),
            Entry("//double", when),
            Entry("/insights/naive", datetime(2026, 1, 1)),
            Entry("/insights/percent-%D8%B9", None),
        ],
    )

    with caplog.at_level(logging.ERROR, logger="tabsira.sitemap"):
        async with client_with() as http:
            listed = await paths(http, "insights")

    assert listed == ["/insights/ok", "/insights/percent-%D8%B9"]
    assert caplog.text.count("dropped") == 8
    assert "'insights/relative'" in caplog.text
    assert "its lastmod has no time zone" in caplog.text


async def test_only_https_pictures_are_listed(client_with, providers, caplog):
    providers[Section.POSTS] = FakeProvider(
        Section.POSTS,
        [
            Entry(
                "/posts/a",
                None,
                (
                    "https://cdn.tabsira.me/a.jpg",
                    "http://insecure.example/b.jpg",
                    "/relative/c.jpg",
                    "javascript:alert(1)",
                    "https://bad host/d.jpg",
                ),
            )
        ],
    )

    with caplog.at_level(logging.WARNING, logger="tabsira.sitemap"):
        async with client_with() as http:
            (entry,) = (await http.get("/sitemap/posts")).json()

    assert entry["images"] == ["https://cdn.tabsira.me/a.jpg"]
    assert entry["lastmod"] is None
    assert "/posts/a lists an image that is not https" in caplog.text


class Greedy:
    """A provider that ignores the page size and returns ten entries."""

    section = Section.PROFILES

    async def pages(self, db: Any, page_size: int) -> list[PageStamp]:
        return []

    async def entries(self, db: Any, page: int, page_size: int) -> list[Entry]:
        return [Entry(f"/u/p{n}") for n in range(10)]


async def test_a_provider_that_returns_too_much_is_cut_to_the_page_size(client_with, providers):
    providers[Section.PROFILES] = Greedy()

    async with client_with(sitemap_page_size=3) as http:
        listed = await paths(http, "profiles")

    assert listed == ["/u/p0", "/u/p1", "/u/p2"]


# ─── Settings and the schema ──────────────────────────────────────────────────


def test_the_page_size_is_between_one_and_the_protocols_fifty_thousand(make_settings):
    assert make_settings().sitemap_page_size == 10_000
    assert make_settings(sitemap_page_size=50_000).sitemap_page_size == 50_000
    assert make_settings(sitemap_page_size=1).sitemap_page_size == 1
    for bad in (0, 50_001, -5):
        with pytest.raises(ValidationError):
            make_settings(sitemap_page_size=bad)


async def test_the_routes_are_in_the_published_schema(client):
    schema = (await client.get("/openapi.json")).json()

    assert {"/sitemap", "/sitemap/{section}"} <= set(schema["paths"])
    assert schema["paths"]["/sitemap"]["get"]["tags"] == ["sitemap"]
    assert schema["components"]["schemas"]["Section"]["enum"] == SECTIONS
    assert {"SitemapIndex", "SitemapPage", "SitemapEntry"} <= set(schema["components"]["schemas"])
