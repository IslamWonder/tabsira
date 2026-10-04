"""The sitemap as the web app reads it: sections cut into pages, and one page of entries."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.services.sitemap_service import Section


class SitemapPage(BaseModel):
    """One page of a section: its number from 0, and the newest `lastmod` it holds."""

    page: int
    lastmod: datetime | None = None


class SitemapIndex(BaseModel):
    """
    The sitemap index: how every advertised section is cut into pages.

    A section whose feature is off is missing; a section with nothing to list has no pages.
    """

    page_size: int
    sections: dict[Section, list[SitemapPage]]


class SitemapEntry(BaseModel):
    """One URL: a path of the web app (the web app adds the origin), its change date, its pictures."""

    path: str
    lastmod: datetime | None = None
    images: list[str] = Field(default_factory=list)
