"""
What the sitemap lists: every public page worth a search engine's visit (decision 29).

The web app writes one sitemap index and one sitemap per section and page
(`docs/SEO.md`, section 1) from the two routes of `routers/sitemap.py`. This module decides
which sections exist, which of them are advertised, how each one is cut into pages and what
each page holds.

The sections are `static`, `insights`, `posts`, `places` and `profiles`. Each is backed by a
provider; a feature plugs in by calling `register` with a provider for its section, so this
module needs no change when a feature arrives. Until then the section has an empty provider and
lists nothing.

Rules every provider keeps, and the service enforces what it can:

- **Only public content.** A provider lists what a stranger may read: public, published,
  non-withdrawn, by an account in good standing. Never a draft, a private insight, an exact
  location or anything of a sensitive scene. A withdrawn item leaves the list at once.
- **One URL form.** An entry is a path of the web app: it starts with `/`, has no trailing
  slash (except the home page), no query and no fragment, and is percent-encoded. The web app
  adds the origin. An entry that breaks this is dropped and logged, never listed.
- **`lastmod` is the record's own change date**, in UTC, never the time of the request or of
  a build; `None` when it is not known.
- **Pages are cut in a stable order** (by id or creation, oldest first), so a new record lands
  in the last page and the pages before it keep their contents and their `lastmod`.
- **Images are absolute `https://` addresses of pictures the page itself shows**, and only of
  photos their owner published.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings

log = logging.getLogger("tabsira.sitemap")


class Section(StrEnum):
    """A kind of public page. The names are part of the web app's URLs for the child sitemaps."""

    STATIC = "static"
    INSIGHTS = "insights"
    POSTS = "posts"
    PLACES = "places"
    PROFILES = "profiles"


# The feature flag that switches a section on, or None for one that is always on. A switched-off
# feature answers 404 on its pages, so its section is not advertised either.
SECTION_FLAGS: dict[Section, str | None] = {
    Section.STATIC: None,
    # A public insight is a saved one that its owner made public.
    Section.INSIGHTS: "feature_world",
    Section.POSTS: "feature_social",
    Section.PLACES: "feature_atlas",
    Section.PROFILES: "feature_social",
}


@dataclass(frozen=True)
class Entry:
    """One URL of a sitemap: a path, when it last changed, and the pictures it shows."""

    path: str
    lastmod: datetime | None = None
    images: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class PageStamp:
    """One page of a section: its number (from 0) and the newest `lastmod` it holds."""

    page: int
    lastmod: datetime | None


class SitemapProvider(Protocol):
    """
    What a feature implements to list its public pages.

    `pages` cuts the section into pages of at most `page_size` entries and says when each last
    changed; `entries` returns one page, in the same order and cut. Both must be cheap enough
    to run on every crawl: counting and offsetting in SQL, not loading the table.
    """

    section: Section

    async def pages(self, db: AsyncSession, page_size: int) -> list[PageStamp]:
        """Return the pages of the section, from 0, with the newest `lastmod` of each."""

    async def entries(self, db: AsyncSession, page: int, page_size: int) -> list[Entry]:
        """Return the entries of one page, in the order `pages` cut them."""


class EmptyProvider:
    """Lists nothing: what a section has until its feature exists."""

    def __init__(self, section: Section) -> None:
        self.section = section

    async def pages(self, db: AsyncSession, page_size: int) -> list[PageStamp]:
        return []

    async def entries(self, db: AsyncSession, page: int, page_size: int) -> list[Entry]:
        return []


@dataclass(frozen=True)
class StaticPage:
    """A page of the web app that is the same for everyone, and the day its text last changed."""

    path: str
    changed: date


# Change a date when the page's text changes, and not otherwise: a crawler reads it as "this
# page is new", and a date that moves on every deploy teaches it to stop believing the dates.
# The legal pages carry the revision of their text. The home page is the product's own page.
STATIC_PAGES: tuple[StaticPage, ...] = (
    StaticPage("/", date(2026, 10, 4)),
    StaticPage("/terms", date(2026, 10, 4)),
    StaticPage("/privacy", date(2026, 10, 4)),
    StaticPage("/support", date(2026, 10, 4)),
    StaticPage("/sources", date(2026, 10, 5)),
)


def _midnight_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


class StaticProvider:
    """The pages that belong to no user: home, terms, privacy and support."""

    section = Section.STATIC

    def __init__(self, pages: Sequence[StaticPage] = STATIC_PAGES) -> None:
        self._entries = [Entry(path=p.path, lastmod=_midnight_utc(p.changed)) for p in pages]

    def _page(self, page: int, page_size: int) -> list[Entry]:
        return self._entries[page * page_size : (page + 1) * page_size]

    async def pages(self, db: AsyncSession, page_size: int) -> list[PageStamp]:
        count = -(-len(self._entries) // page_size)
        stamps = []
        for number in range(count):
            dates = [entry.lastmod for entry in self._page(number, page_size) if entry.lastmod]
            stamps.append(PageStamp(page=number, lastmod=max(dates, default=None)))
        return stamps

    async def entries(self, db: AsyncSession, page: int, page_size: int) -> list[Entry]:
        return self._page(page, page_size)


def _default_providers() -> dict[Section, SitemapProvider]:
    providers: dict[Section, SitemapProvider] = {
        section: EmptyProvider(section) for section in Section if section is not Section.STATIC
    }
    providers[Section.STATIC] = StaticProvider()
    return providers


# One provider per section. A feature plugs in with `register`, normally when its module is
# imported.
PROVIDERS: dict[Section, SitemapProvider] = _default_providers()


def register(provider: SitemapProvider) -> None:
    """Make `provider` the one that lists its section, replacing the one that was there."""
    PROVIDERS[provider.section] = provider


def enabled_sections(settings: Settings) -> list[Section]:
    """Return the sections to advertise, in order: those whose feature flag is on."""
    return [
        section
        for section in Section
        if (flag := SECTION_FLAGS[section]) is None or bool(getattr(settings, flag))
    ]


async def pages(db: AsyncSession, settings: Settings, section: Section) -> list[PageStamp]:
    """Cut a section into pages, each with the newest `lastmod` it holds."""
    return await PROVIDERS[section].pages(db, settings.sitemap_page_size)


# A path of the web app: RFC 3986 characters only (Arabic is percent-encoded), segments
# separated by single slashes, no trailing slash.
_SEGMENT = r"[A-Za-z0-9._~!$&'()*+,;=:@%-]+"
_PATH = re.compile(rf"^/(?:{_SEGMENT}(?:/{_SEGMENT})*)?$")
_IMAGE = re.compile(r"^https://[^\s<>\"']+$")


def _is_listable(section: Section, entry: Entry) -> bool:
    """Whether an entry follows the rules above; it is logged when it does not."""
    if _PATH.match(entry.path) is None:
        log.error("Sitemap %s: dropped %r, not a path of the web app.", section, entry.path)
        return False
    if entry.lastmod is not None and entry.lastmod.tzinfo is None:
        log.error("Sitemap %s: dropped %s, its lastmod has no time zone.", section, entry.path)
        return False
    return True


def _clean(section: Section, entry: Entry) -> Entry:
    """Return the entry with only the images that are absolute `https://` addresses."""
    images = tuple(image for image in entry.images if _IMAGE.match(image))
    if len(images) != len(entry.images):
        log.warning("Sitemap %s: %s lists an image that is not https.", section, entry.path)
    return Entry(path=entry.path, lastmod=entry.lastmod, images=images)


async def entries(db: AsyncSession, settings: Settings, section: Section, page: int) -> list[Entry]:
    """List one page of a section, in the provider's order, keeping only what may be listed."""
    page_size = settings.sitemap_page_size
    listed = await PROVIDERS[section].entries(db, page, page_size)
    return [_clean(section, entry) for entry in listed[:page_size] if _is_listable(section, entry)]
