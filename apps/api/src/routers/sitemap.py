"""
The sitemap's contents, for the web app to write out as XML (decision 29).

`GET /sitemap` says how each section is cut into pages and when each page last changed (the
sitemap index); `GET /sitemap/{section}?page=` lists one page. What is listed, and why, is in
`services/sitemap_service.py`. Only public content is ever listed, so no route needs a session.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response

from src.deps import DbDep, SettingsDep
from src.errors import AppError, ErrorCode
from src.schemas.sitemap import SitemapEntry, SitemapIndex, SitemapPage
from src.services import sitemap_service
from src.services.sitemap_service import Section

router = APIRouter(prefix="/sitemap", tags=["sitemap"])

# Five minutes: long enough that a crawl of every child does not hit the database five times
# over, short enough that a published page is in the next one.
CACHE_CONTROL = "public, max-age=300"


@router.get("", summary="Every section's pages")
async def sitemap_index(db: DbDep, settings: SettingsDep, response: Response) -> SitemapIndex:
    """
    List the sections that are advertised, each with its pages and their last change.

    A section whose feature is switched off is not listed, and a section with nothing to list
    has no pages.
    """
    response.headers["Cache-Control"] = CACHE_CONTROL
    sections = {}
    for section in sitemap_service.enabled_sections(settings):
        stamps = await sitemap_service.pages(db, settings, section)
        sections[section] = [SitemapPage(page=s.page, lastmod=s.lastmod) for s in stamps]
    return SitemapIndex(page_size=settings.sitemap_page_size, sections=sections)


@router.get("/{section}", summary="One page of a section")
async def sitemap_section(
    section: Section,
    db: DbDep,
    settings: SettingsDep,
    response: Response,
    page: Annotated[int, Query(ge=0)] = 0,
) -> list[SitemapEntry]:
    """
    List one page of a section, in a stable order.

    A page past the last is empty. A section whose feature is off is a 404, like its pages.
    """
    if section not in sitemap_service.enabled_sections(settings):
        raise AppError(ErrorCode.NOT_FOUND, "No such sitemap.", status_code=404)
    response.headers["Cache-Control"] = CACHE_CONTROL
    entries = await sitemap_service.entries(db, settings, section, page)
    return [SitemapEntry(path=e.path, lastmod=e.lastmod, images=list(e.images)) for e in entries]
