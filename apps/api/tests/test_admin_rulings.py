"""
The rulings queue: the hadiths waiting for a dorar.net ruling, their pages, and recording one.

The text of a hadith is shown byte for byte with its stored hash and is never a field; the
dorar.net link is a search the editor opens, never a call the server makes; a ruling goes
through the same service as the command line, and the audit log keeps names, never values.
"""

from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from src.models import AuditAction, HadithClassification, HadithRuling
from src.scripture.rulings import enqueue_demand, find_hadith, is_eligible
from tests.scripture.fixtures import store_hadiths
from tests.support_admin import audit_rows, csrf_of

QUEUE = "/admin/rulings-queue"
DORAR_PAGE = "https://dorar.net/h/abc123"


def page_of(hadith_id: int) -> str:
    return f"{QUEUE}/hadith/{hadith_id}"


def ruling_form(**changes: str) -> dict[str, str]:
    values = {
        "ruling_text": " [صحيح] ",
        "scholar": "الألباني",
        "source_book": "صحيح الجامع",
        "page": "12",
        "dorar_url": DORAR_PAGE,
        "classification": HadithClassification.SAHIH.value,
        "editor_name": "Admin",
    }
    return {**values, **changes}


@pytest.fixture
async def hadiths(db_session):
    """The fixture books, with two hadiths waiting in the queue: one wanted more than the other."""
    await store_hadiths(db_session)
    wanted = await find_hadith(db_session, "bukhari", "1032")
    other = await find_hadith(db_session, "muslim", "3")
    assert wanted is not None and other is not None
    for _ in range(3):
        await enqueue_demand(db_session, wanted.id)
    await enqueue_demand(db_session, other.id)
    await db_session.flush()
    return wanted, other


async def record(http, hadith_id, **changes):
    return await http.post(
        f"{page_of(hadith_id)}/record",
        data={**ruling_form(**changes), "csrf_token": await csrf_of(http)},
    )


# ─── The queue ─────────────────────────────────────────────────────


async def test_the_queue_lists_the_most_wanted_first_with_a_dorar_search_to_open(
    admin, db_session, hadiths
):
    http, me = admin
    wanted, other = hadiths

    page = await http.get(QUEUE)

    assert page.status_code == 200
    body = page.text
    assert "2 waiting" in body
    assert body.index(f"bukhari {wanted.number}") < body.index(f"muslim {other.number}")
    assert page_of(wanted.id) in body
    links = re.findall(r'href="(https://dorar\.net[^"]*)"', body)
    assert len(links) == 2
    parts = urlsplit(links[0].replace("&amp;", "&"))
    assert (parts.scheme, parts.hostname, parts.path) == ("https", "dorar.net", "/hadith/search")
    assert parse_qs(parts.query)["st"] == ["w"]
    assert parse_qs(parts.query)["q"][0]
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.LIST][-1]
    assert (row.model, row.admin_user_id, row.details) == ("rulings-queue", me.id, None)


async def test_an_empty_queue_says_so(admin, db_session):
    http, _ = admin
    await store_hadiths(db_session)

    page = await http.get(QUEUE)

    assert page.status_code == 200
    assert "No hadith is waiting for a ruling." in page.text


# ─── A hadith's page ───────────────────────────────────────────────


async def test_a_hadith_page_shows_its_text_whole_with_its_hash_and_never_as_a_field(
    admin, db_session, hadiths
):
    http, me = admin
    wanted, _ = hadiths

    page = await http.get(page_of(wanted.id))

    assert page.status_code == 200
    body = page.text
    shown = re.search(r'id="hadith-text" dir="rtl" lang="ar">(.*?)</p>', body, re.DOTALL)
    assert shown is not None
    # The page escapes HTML the way a browser undoes it; what the browser shows is the stored text.
    displayed = html.unescape(shown.group(1))
    assert displayed == wanted.text
    assert hashlib.sha256(displayed.encode("utf-8")).hexdigest() == wanted.text_sha256
    assert f'id="hadith-hash">{wanted.text_sha256}<' in body
    assert displayed[:40] not in html.unescape(
        "".join(re.findall(r"<(?:input|textarea)[^>]*>[^<]*", body))
    )
    assert 'name="text"' not in body
    assert "wanted 3 times" in body
    assert "None yet." in body
    assert 'Eligible as evidence</dt><dd class="col-8">no' in body
    for field in (
        "ruling_text",
        "scholar",
        "source_book",
        "page",
        "dorar_url",
        "classification",
        "editor_name",
    ):
        assert f'name="{field}"' in body
    assert 'name="editor_name" class="form-control" value="Admin"' in body
    assert f'action="https://admin.tabsira.test{page_of(wanted.id)}/record"' in body
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.VIEW][-1]
    assert (row.model, row.record_id, row.admin_user_id) == (
        "rulings-queue",
        str(wanted.id),
        me.id,
    )


async def test_an_unknown_hadith_has_no_page(admin, db_session):
    http, _ = admin
    await store_hadiths(db_session)

    page = await http.get(page_of(999_999))
    posted = await http.post(
        f"{page_of(999_999)}/record", data={**ruling_form(), "csrf_token": await csrf_of(http)}
    )

    assert page.status_code == 404
    assert "No stored hadith has this id." in page.text
    assert posted.status_code == 404


# ─── Recording a ruling ────────────────────────────────────────────


async def test_recording_a_ruling_takes_the_hadith_off_the_queue_and_audits_the_field_names(
    admin, db_session, hadiths
):
    http, me = admin
    wanted, other = hadiths

    response = await record(http, wanted.id)

    assert response.status_code == 303
    rulings = (await db_session.scalars(select(HadithRuling))).all()
    assert len(rulings) == 1
    ruling = rulings[0]
    assert response.headers["location"] == f"https://admin.tabsira.test{QUEUE}?recorded={ruling.id}"
    assert (ruling.hadith_id, ruling.recorded_by, ruling.editor_name) == (wanted.id, me.id, "Admin")
    assert ruling.ruling_text == " [صحيح] "
    assert ruling.classification is HadithClassification.SAHIH
    assert await is_eligible(db_session, wanted.id)

    created = [r for r in await audit_rows(db_session) if r.action is AuditAction.CREATE][-1]
    assert (created.model, created.record_id, created.admin_user_id) == (
        "hadith-ruling",
        str(ruling.id),
        me.id,
    )
    assert created.details == {
        "fields": [
            "classification",
            "dorar_url",
            "editor_name",
            "page",
            "ruling_text",
            "scholar",
            "source_book",
        ]
    }
    assert "الألباني" not in repr(created.details)

    queue = await http.get(response.headers["location"])
    assert f"Ruling {ruling.id} recorded." in queue.text
    assert "1 waiting" in queue.text
    assert f"bukhari {wanted.number}" not in queue.text
    assert f"muslim {other.number}" in queue.text

    page = await http.get(page_of(wanted.id))
    assert 'In the queue</dt>\n        <dd class="col-8">no' in page.text
    assert 'Eligible as evidence</dt><dd class="col-8">yes' in page.text
    assert f"/admin/hadith-ruling/details/{ruling.id}" in page.text


async def test_a_later_ruling_is_the_one_in_force(admin, db_session, hadiths):
    http, _ = admin
    wanted, _ = hadiths

    await record(http, wanted.id)
    await record(http, wanted.id, classification=HadithClassification.DAIF.value, page="13")

    assert not await is_eligible(db_session, wanted.id)
    assert len((await db_session.scalars(select(HadithRuling))).all()) == 2


async def test_a_refused_ruling_names_its_fields_and_records_nothing(admin, db_session, hadiths):
    http, _ = admin
    wanted, _ = hadiths

    response = await record(http, wanted.id, dorar_url="https://example.com/h/1", scholar="  ")

    assert response.status_code == 400
    assert "The ruling was not recorded. Check: dorar url, scholar." in response.text
    assert 'value="https://example.com/h/1"' in response.text
    assert (await db_session.scalars(select(HadithRuling))).all() == []
    assert not [r for r in await audit_rows(db_session) if r.action is AuditAction.CREATE]
    assert "wanted 3 times" in response.text


async def test_a_ruling_with_a_missing_field_is_refused(admin, db_session, hadiths):
    http, _ = admin
    wanted, _ = hadiths

    response = await http.post(
        f"{page_of(wanted.id)}/record",
        data={"ruling_text": "x", "csrf_token": await csrf_of(http)},
    )

    assert response.status_code == 400
    assert "Check: classification, dorar url, editor name, page, scholar, source book." in (
        response.text
    )


async def test_recording_is_a_post_with_the_token(admin, db_session, hadiths):
    http, _ = admin
    wanted, _ = hadiths

    assert (await http.get(f"{page_of(wanted.id)}/record")).status_code == 405
    assert (await http.post(f"{page_of(wanted.id)}/record", data=ruling_form())).status_code == 403
    assert (await db_session.scalars(select(HadithRuling))).all() == []


# ─── The history view ──────────────────────────────────────────────


async def test_the_rulings_history_is_listed_and_shown_but_never_changed(
    admin, db_session, hadiths
):
    http, _ = admin
    wanted, _ = hadiths
    await record(http, wanted.id)
    ruling = (await db_session.scalars(select(HadithRuling))).one()
    token = await csrf_of(http)

    listing = await http.get("/admin/hadith-ruling/list")
    page = await http.get(f"/admin/hadith-ruling/details/{ruling.id}")

    assert listing.status_code == 200
    assert "الألباني" in listing.text
    assert "[صحيح]" not in listing.text
    assert page.status_code == 200
    assert "[صحيح]" in page.text
    assert DORAR_PAGE in page.text
    assert (await http.get("/admin/hadith-ruling/create")).status_code == 403
    assert (await http.get(f"/admin/hadith-ruling/edit/{ruling.id}")).status_code == 403
    assert (
        await http.delete(
            f"/admin/hadith-ruling/delete?pks={ruling.id}", headers={"X-CSRF-Token": token}
        )
    ).status_code == 403
    assert (await http.get("/admin/hadith-ruling/export/csv")).status_code == 403


@pytest.mark.parametrize("path", [QUEUE, f"{QUEUE}/hadith/1", "/admin/hadith-ruling/list"])
async def test_a_signed_out_browser_reaches_nothing(anon, path):
    assert (await anon.get(path)).status_code == 302
