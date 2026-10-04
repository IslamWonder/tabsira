"""Publishing an insight, withdrawing it, and reading it as a stranger (task 09.1)."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from src import clock
from src.models import HadithClassification, Insight, InsightOrigin
from src.models.user import User
from src.owner import Owner
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest, make_account, rule, sign_in
from tests.scripture.fixtures import hadith_text, verse_text

PRIVATE_KEYS = {
    "scan_id",
    "anchor",
    "chat",
    "action",
    "image",
    "place_id",
    "why",
    "learning_unit",
    "completed_at",
    "created_at",
    "origin",
}


async def keep(store, user_id, *, scan: bool = True, **values) -> int:
    async with store() as db:
        if scan:
            row = scan_row(Owner(user_id=user_id), status="done", **values.pop("scan_values", {}))
            db.add(row)
            await db.flush()
            values.setdefault("scan_id", row.id)
        insight = insight_row(Owner(user_id=user_id), **values)
        db.add(insight)
        await db.commit()
        return insight.id


async def verified_account(store, browser, **columns) -> User:
    user = await make_account(store)
    async with store() as db:
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(email_verified_at=clock.utcnow(), **columns)
        )
        await db.commit()
    await sign_in(browser)
    return user


async def test_the_owner_publishes_and_a_stranger_reads_scripture_as_stored(browser, other, store):
    user = await verified_account(store, browser)
    insight_id = await keep(store, user.id)
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()

    done = await browser.put(f"/insights/{insight_id}/publication")

    assert done.status_code == 200
    assert done.json()["published"] is True
    assert done.json()["path"] == f"/insights/{insight_id}"
    response = await other.get(f"/public/insights/{insight_id}")
    body = response.json()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    verse = body["quran"]["verse"]
    assert verse["text"] == verse_text(30, 50)
    assert hashlib.sha256(verse["text"].encode()).hexdigest() == verse["sha256"]
    hadith = body["hadith"]["hadith"]
    assert hadith["text"] == hadith_text("bukhari", 1032)
    assert hashlib.sha256(hadith["text"].encode()).hexdigest() == hadith["sha256"]
    assert (body["hadith_status"], body["pair_complete"]) == ("shown", True)
    assert body["small_step"]["label"] == "من السنة"
    assert body["disclosure"].startswith("تبصرة أداة مدعومة")
    assert PRIVATE_KEYS.isdisjoint(body)
    assert body["author"] is None
    assert "reader@example.com" not in response.text
    assert "Reader" not in response.text
    assert str(user.id) not in response.text


async def test_the_author_is_the_handle_and_name_the_owner_chose_and_nothing_else(
    browser, other, store
):
    user = await verified_account(store, browser, handle="basira_fan", public_name="قارئ")
    insight_id = await keep(store, user.id)
    await browser.put(f"/insights/{insight_id}/publication")

    body = (await other.get(f"/public/insights/{insight_id}")).json()

    assert body["author"] == {"handle": "basira_fan", "public_name": "قارئ"}
    assert body["hadith_status"] == "awaiting_verification"
    assert body["hadith"] is None
    assert body["small_step"] is None


async def test_asking_twice_changes_nothing_and_the_owner_sees_the_state(browser, store):
    user = await verified_account(store, browser)
    insight_id = await keep(store, user.id)

    first = (await browser.put(f"/insights/{insight_id}/publication")).json()
    second = (await browser.put(f"/insights/{insight_id}/publication")).json()
    detail = (await browser.get(f"/insights/{insight_id}")).json()

    assert first == second
    assert detail["published_at"] == first["published_at"]


async def test_an_unpublished_withdrawn_or_unknown_insight_answers_404(browser, other, store):
    user = await verified_account(store, browser)
    insight_id = await keep(store, user.id)

    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 404
    await browser.put(f"/insights/{insight_id}/publication")
    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 200

    withdrawn = await browser.delete(f"/insights/{insight_id}/publication")
    again = await browser.delete(f"/insights/{insight_id}/publication")

    assert withdrawn.json() == again.json()
    assert withdrawn.json()["published"] is False
    assert withdrawn.json()["path"] is None
    gone = await other.get(f"/public/insights/{insight_id}")
    assert (gone.status_code, gone.headers["cache-control"]) == (404, "no-store")
    assert (await other.get("/public/insights/999")).status_code == 404
    assert (await browser.get(f"/insights/{insight_id}")).json()["published_at"] is None
    async with store() as db:
        assert (await db.get(Insight, insight_id)).withdrawn_at is not None

    assert (await browser.put(f"/insights/{insight_id}/publication")).json()["published"] is True
    async with store() as db:
        assert (await db.get(Insight, insight_id)).withdrawn_at is None


async def test_a_guest_or_an_unverified_account_cannot_publish(
    browser, other, store, flow_settings
):
    guest = await as_guest(other, store, flow_settings)
    async with store() as db:
        row = insight_row(
            guest, origin=InsightOrigin.TUTORIAL, tutorial_slug="rain", tutorial_scene="rain"
        )
        db.add(row)
        await db.commit()
        guest_insight = row.id
    assert (await other.put(f"/insights/{guest_insight}/publication")).status_code == 401
    assert (await other.get(f"/public/insights/{guest_insight}")).status_code == 404

    user = await make_account(store)
    await sign_in(browser)
    insight_id = await keep(store, user.id)
    refused = await browser.put(f"/insights/{insight_id}/publication")
    assert (refused.status_code, refused.json()["error"]) == (403, "EMAIL_NOT_VERIFIED")
    assert (await browser.delete(f"/insights/{insight_id}/publication")).status_code == 403


async def test_another_owners_insight_cannot_be_published_or_withdrawn(browser, store):
    mine = await verified_account(store, browser)
    stranger = await make_account(store, "other@example.com")
    theirs = await keep(store, stranger.id)
    assert mine.id != stranger.id

    assert (await browser.put(f"/insights/{theirs}/publication")).status_code == 404
    assert (await browser.delete(f"/insights/{theirs}/publication")).status_code == 404


@pytest.mark.parametrize(
    ("values", "scan_values"),
    [
        ({}, {"sensitive": True}),
        ({"quran_surah": None, "quran_ayah": None, "quran_evidence": None}, {}),
        ({"title": verse_text(30, 50)}, {}),
        ({"explanation": [{"section": "seen", "text": verse_text(30, 50), "sources": []}]}, {}),
        (
            {"small_step": {"text": verse_text(30, 50), "kind": "reflection", "grounded_in": []}},
            {},
        ),
    ],
    ids=["sensitive", "no text to show", "scripture in title", "in explanation", "in step"],
)
async def test_an_insight_that_may_not_be_public_is_refused(browser, store, values, scan_values):
    user = await verified_account(store, browser)
    insight_id = await keep(store, user.id, scan_values=scan_values, **values)

    response = await browser.put(f"/insights/{insight_id}/publication")

    assert (response.status_code, response.json()["error"]) == (
        409,
        "INSIGHT_NOT_PUBLISHABLE",
    )
    async with store() as db:
        assert (await db.get(Insight, insight_id)).published_at is None


async def test_a_weak_hadith_is_not_shown_publicly_either(browser, other, store):
    user = await verified_account(store, browser)
    insight_id = await keep(store, user.id)
    async with store() as db:
        await rule(db, "bukhari", "1032", HadithClassification.DAIF)
        await db.commit()
    await browser.put(f"/insights/{insight_id}/publication")

    body = (await other.get(f"/public/insights/{insight_id}")).json()

    assert (body["hadith"], body["hadith_status"]) == (None, "none")


async def test_a_prepared_example_keeps_its_label(browser, other, store):
    user = await verified_account(store, browser)
    insight_id = await keep(store, user.id, engine="prepared")
    await browser.put(f"/insights/{insight_id}/publication")

    body = (await other.get(f"/public/insights/{insight_id}")).json()

    assert body["label"] == "مثال موثّق مُعدّ"


async def test_a_closed_account_or_a_deleted_one_takes_its_insights_off(browser, other, store):
    user = await verified_account(store, browser)
    insight_id = await keep(store, user.id)
    await browser.put(f"/insights/{insight_id}/publication")

    for column in ({"is_active": False}, {"is_active": True, "deleted_at": clock.utcnow()}):
        async with store() as db:
            await db.execute(update(User).where(User.id == user.id).values(**column))
            await db.commit()
        assert (await other.get(f"/public/insights/{insight_id}")).status_code == 404


async def test_the_public_route_answers_404_while_the_feature_is_off(flow_app, other):
    from src.deps import get_app_settings

    off = flow_app.state.settings.model_copy(update={"feature_world": False})
    flow_app.dependency_overrides[get_app_settings] = lambda: off

    response = await other.get("/public/insights/1")

    assert (response.status_code, response.json()["error"]) == (404, "FEATURE_DISABLED")


async def test_the_database_refuses_a_public_insight_without_an_account(
    store, flow_settings, browser
):
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        db.add(
            insight_row(
                owner,
                origin=InsightOrigin.TUTORIAL,
                tutorial_slug="rain",
                tutorial_scene="rain",
                published_at=clock.utcnow(),
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_a_kept_tutorial_insight_with_no_scan_and_no_step_can_be_public(
    browser, other, store
):
    user = await verified_account(store, browser)
    insight_id = await keep(
        store,
        user.id,
        scan=False,
        origin=InsightOrigin.TUTORIAL,
        tutorial_slug="rain",
        tutorial_scene="rain",
        small_step=None,
    )

    done = await browser.put(f"/insights/{insight_id}/publication")

    assert done.status_code == 200
    assert (await other.get(f"/public/insights/{insight_id}")).json()["small_step"] is None


async def test_the_account_export_carries_the_publication_times(browser, store):
    user = await verified_account(store, browser)
    insight_id = await keep(store, user.id)
    await browser.put(f"/insights/{insight_id}/publication")
    await browser.delete(f"/insights/{insight_id}/publication")

    export = (await browser.get("/account/export")).json()

    kept = export["learning"]["insights"][0]
    assert kept["published_at"] is None
    assert kept["withdrawn_at"] is not None
