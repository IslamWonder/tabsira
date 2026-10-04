"""Publishing an insight (v2 §18): the owner makes it public, anyone reads it, nothing private shows."""

from __future__ import annotations

import hashlib

from sqlalchemy import text, update

from src import clock
from src.models import AgeRange, HadithClassification, Profile, User
from src.owner import Owner
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest, make_account, rule, sign_in
from tests.scripture.fixtures import hadith_text, verse_text

PUBLIC_KEYS = {
    "id",
    "path",
    "title",
    "glimpse",
    "label",
    "relation",
    "relation_label",
    "quran",
    "hadith",
    "explanation_tag",
    "explanation",
    "why",
    "small_step",
    "author",
    "published_at",
    "disclosure",
}
# Words of the owner's own view and account that a public page must never carry.
PRIVATE_WORDS = (
    '"chat"',
    '"scan_id"',
    "/scans/",
    "personalised_because",
    '"place_id"',
    "learning_unit",
    '"action"',
    "completed_at",
    "reader@example.com",
    "Reader",
    "religious_background",
    "gender",
    "age_range",
    # The profile values the fixture account declares, and the engine's personal reason.
    '"muslim"',
    '"woman"',
    '"25_39"',
)


async def keep(store, owner: Owner, *, scan: bool = True, **values) -> int:
    async with store() as db:
        if scan:
            row = scan_row(owner, status="done", **values.pop("scan_values", {}))
            db.add(row)
            await db.flush()
            values.setdefault("scan_id", row.id)
        insight = insight_row(owner, **values)
        db.add(insight)
        await db.commit()
        return insight.id


async def verified_account(
    store,
    email: str = "reader@example.com",
    public_name: str | None = None,
    age_range: AgeRange = AgeRange.FROM_25_TO_39,
) -> Owner:
    """An account that proved its address and answered its profile, with or without a public name."""
    user = await make_account(store, email)
    async with store() as db:
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(email_verified_at=clock.utcnow(), public_name=public_name)
        )
        await db.execute(
            update(Profile)
            .where(Profile.user_id == user.id)
            .values(
                age_range=age_range,
                religious_background="muslim",
                gender="woman",
            )
        )
        await db.commit()
    return Owner(user_id=user.id)


async def test_a_verified_owner_publishes_and_anyone_reads_the_texts_exactly_as_stored(
    browser, other, store, flow_settings
):
    owner = await verified_account(store, public_name="قارئ")
    await sign_in(browser)
    insight_id = await keep(store, owner)
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()

    published = await browser.post(f"/insights/{insight_id}/publish")
    again = await browser.post(f"/insights/{insight_id}/publish")
    mine = (await browser.get(f"/insights/{insight_id}")).json()
    public = await other.get(f"/public/insights/{insight_id}")

    assert published.status_code == 200, published.text
    state = published.json()
    assert (state["published"], state["path"]) == (True, f"/i/{insight_id}")
    assert state["published_at"] is not None
    # Publishing twice keeps the first time.
    assert again.json() == state
    assert mine["publication"] == state
    assert public.status_code == 200, public.text
    assert public.headers["cache-control"] == "public, max-age=300"
    body = public.json()
    assert set(body) == PUBLIC_KEYS
    assert (body["id"], body["path"], body["published_at"]) == (
        str(insight_id),
        f"/i/{insight_id}",
        state["published_at"],
    )
    verse = body["quran"]["verse"]
    assert verse["text"] == verse_text(30, 50)
    assert hashlib.sha256(verse["text"].encode()).hexdigest() == verse["sha256"]
    hadith = body["hadith"]["hadith"]
    assert hadith["text"] == hadith_text("bukhari", 1032)
    assert hashlib.sha256(hadith["text"].encode()).hexdigest() == hadith["sha256"]
    assert body["author"] == {"public_name": "قارئ"}
    assert body["why"] == {"visible_clues": ["قطرات"], "concept": "الإحياء", "limits": []}
    assert body["small_step"]["label"] == "من السنة"
    assert body["label"] is None
    assert body["disclosure"].startswith("تبصرة أداة مدعومة")
    for private in PRIVATE_WORDS:
        assert private not in public.text, private


async def test_without_a_public_name_the_page_names_nobody_and_a_prepared_insight_says_so(
    browser, other, store, flow_settings
):
    owner = await verified_account(store)
    await sign_in(browser)
    insight_id = await keep(
        store,
        owner,
        engine="prepared",
        hadith_collection=None,
        hadith_number=None,
        small_step=None,
    )

    assert (await browser.post(f"/insights/{insight_id}/publish")).status_code == 200
    body = (await other.get(f"/public/insights/{insight_id}")).json()

    assert body["author"] is None
    assert body["label"] == "مثال موثّق مُعدّ"
    assert body["hadith"] is None
    assert body["small_step"] is None
    assert "Reader" not in str(body)


async def test_private_withdrawn_and_missing_insights_answer_the_same_404(
    browser, other, store, flow_settings
):
    owner = await verified_account(store)
    await sign_in(browser)
    insight_id = await keep(store, owner)

    private = await other.get(f"/public/insights/{insight_id}")
    assert (private.status_code, private.json()["error"]) == (404, "NOT_FOUND")
    assert (await browser.post(f"/insights/{insight_id}/publish")).status_code == 200
    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 200

    withdrawn = await browser.delete(f"/insights/{insight_id}/publish")
    again = await browser.delete(f"/insights/{insight_id}/publish")

    assert withdrawn.json() == {"published": False, "published_at": None, "path": None}
    assert again.json() == withdrawn.json()
    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 404
    assert (await browser.get(f"/insights/{insight_id}")).json()["publication"] == withdrawn.json()
    assert (await other.get(f"/public/insights/{7_314_159_265_358_979_323}")).status_code == 404


async def test_only_the_verified_owner_publishes_or_withdraws(browser, other, store, flow_settings):
    guest = await as_guest(browser, store, flow_settings)
    guest_insight = await keep(store, guest)
    unverified = await make_account(store, "new@example.com")
    owner = await verified_account(store, "owner@example.com")
    insight_id = await keep(store, owner)

    as_guest_response = await browser.post(f"/insights/{guest_insight}/publish")
    assert (as_guest_response.status_code, as_guest_response.json()["error"]) == (
        401,
        "UNAUTHORIZED",
    )

    await sign_in(other, "new@example.com")
    unverified_response = await other.post(f"/insights/{insight_id}/publish")
    assert (unverified_response.status_code, unverified_response.json()["error"]) == (
        403,
        "EMAIL_NOT_VERIFIED",
    )
    async with store() as db:
        await db.execute(
            update(User).where(User.id == unverified.id).values(email_verified_at=clock.utcnow())
        )
        await db.commit()
    for method in ("POST", "DELETE"):
        response = await other.request(method, f"/insights/{insight_id}/publish")
        assert (response.status_code, response.json()["error"]) == (404, "NOT_FOUND")
    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 404


async def test_a_simulation_a_personal_an_unverified_and_a_leaking_insight_are_refused(
    browser, store, flow_settings
):
    owner = await verified_account(store)
    await sign_in(browser)
    simulation = await keep(store, owner, engine="demo")
    personal = await keep(
        store,
        owner,
        why={"visible_clues": [], "concept": "x", "limits": [], "personalised_because": "هدفك"},
    )
    # A hadith waiting for its ruling and no verse: nothing is shown yet.
    unverified = await keep(store, owner, quran_surah=None, quran_ayah=None, quran_evidence=None)
    leaking = await keep(store, owner, title=verse_text(30, 50))
    # The leak guard reads every text the page prints, the clues and the match included.
    leaking_clue = await keep(
        store, owner, why={"visible_clues": [verse_text(30, 50)], "concept": "x", "limits": []}
    )
    # A copy of a stored hadith with its marks stripped is still a copy of the store.
    plain = "".join(c for c in hadith_text("bukhari", 1032) if not "\u064b" <= c <= "\u0652")
    copied = await keep(store, owner, glimpse=plain)

    for insight_id, reason in (
        (simulation, "simulation"),
        (personal, "in person"),
        (unverified, "verified and shown"),
        (leaking, "looks like scripture"),
        (leaking_clue, "looks like scripture"),
        (copied, "looks like scripture"),
    ):
        response = await browser.post(f"/insights/{insight_id}/publish")
        assert response.status_code == 409, response.text
        assert response.json()["error"] == "INSIGHT_NOT_PUBLISHABLE"
        assert reason in response.json()["detail"]
        assert (await browser.get(f"/insights/{insight_id}")).json()["publication"][
            "published"
        ] is False


async def test_a_page_whose_texts_are_no_longer_shown_or_whose_owner_is_gone_vanishes(
    browser, other, store, flow_settings
):
    owner = await verified_account(store)
    await sign_in(browser)
    insight_id = await keep(store, owner, hadith_collection=None, hadith_number=None)
    assert (await browser.post(f"/insights/{insight_id}/publish")).status_code == 200
    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 200

    async with store() as db:
        await db.execute(
            text("UPDATE app.insights SET quran_surah = NULL, quran_ayah = NULL WHERE id = :id"),
            {"id": insight_id},
        )
        await db.commit()
    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 404

    async with store() as db:
        await db.execute(
            text("UPDATE app.insights SET quran_surah = 30, quran_ayah = 50 WHERE id = :id"),
            {"id": insight_id},
        )
        await db.execute(update(User).where(User.id == owner.user_id).values(is_active=False))
        await db.commit()
    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 404


async def test_published_insights_are_listed_in_the_sitemap_oldest_first_until_withdrawn(
    browser, other, store, flow_settings
):
    owner = await verified_account(store)
    await sign_in(browser)
    first = await keep(store, owner)
    second = await keep(store, owner)
    withdrawn = await keep(store, owner)
    await keep(store, owner)  # stays private
    for insight_id in (second, first, withdrawn):
        assert (await browser.post(f"/insights/{insight_id}/publish")).status_code == 200
    assert (await browser.delete(f"/insights/{withdrawn}/publish")).status_code == 200

    index = (await other.get("/sitemap")).json()
    page = (await other.get("/sitemap/insights", params={"page": 0})).json()

    newest = (await browser.get(f"/insights/{first}")).json()["publication"]["published_at"]
    assert index["sections"]["insights"] == [{"page": 0, "lastmod": newest}]
    assert [entry["path"] for entry in page] == [f"/i/{first}", f"/i/{second}"]
    assert all(entry["images"] == [] for entry in page)
    assert (await other.get("/sitemap/insights", params={"page": 1})).json() == []


async def test_the_export_carries_the_publication_time(browser, store, flow_settings):
    owner = await verified_account(store)
    await sign_in(browser)
    insight_id = await keep(store, owner)
    assert (await browser.post(f"/insights/{insight_id}/publish")).status_code == 200

    export = (await browser.get("/account/export")).json()

    insights = export["learning"]["insights"]
    assert [insight["id"] for insight in insights] == [str(insight_id)]
    assert insights[0]["published_at"] is not None


async def test_an_account_declared_under_13_has_no_public_publishing(
    browser, other, store, flow_settings
):
    owner = await verified_account(store)
    await sign_in(browser)
    insight_id = await keep(store, owner)
    assert (await browser.post(f"/insights/{insight_id}/publish")).status_code == 200
    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 200
    assert [e["path"] for e in (await other.get("/sitemap/insights")).json()] == [
        f"/i/{insight_id}"
    ]

    # The age is declared after publishing: the page and the listing go at once.
    async with store() as db:
        await db.execute(
            update(Profile)
            .where(Profile.user_id == owner.user_id)
            .values(age_range=AgeRange.UNDER_13)
        )
        await db.commit()

    assert (await other.get(f"/public/insights/{insight_id}")).status_code == 404
    assert (await other.get("/sitemap/insights")).json() == []
    second = await keep(store, owner)
    refused = await browser.post(f"/insights/{second}/publish")
    assert (refused.status_code, refused.json()["error"]) == (409, "INSIGHT_NOT_PUBLISHABLE")
    assert "under 13" in refused.json()["detail"]
    # Withdrawing stays possible.
    assert (await browser.delete(f"/insights/{insight_id}/publish")).json()["published"] is False


async def test_a_hadith_only_insight_reads_and_a_disabled_owner_leaves_the_sitemap(
    browser, other, store, flow_settings
):
    owner = await verified_account(store)
    await sign_in(browser)
    insight_id = await keep(store, owner, quran_surah=None, quran_ayah=None, quran_evidence=None)
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()
    assert (await browser.post(f"/insights/{insight_id}/publish")).status_code == 200

    body = (await other.get(f"/public/insights/{insight_id}")).json()
    assert body["quran"] is None
    assert body["hadith"]["hadith"]["text"] == hadith_text("bukhari", 1032)
    assert [e["path"] for e in (await other.get("/sitemap/insights")).json()] == [
        f"/i/{insight_id}"
    ]

    async with store() as db:
        await db.execute(update(User).where(User.id == owner.user_id).values(is_active=False))
        await db.commit()
    assert (await other.get("/sitemap/insights")).json() == []


async def test_the_routes_follow_the_world_feature_like_the_sitemap_section(
    store, make_settings, maker, redis, queue, fetcher, model
):
    from src.database import get_db
    from src.main import create_app
    from tests.conftest import browser_for

    settings = make_settings(password_bcrypt_rounds=4, feature_world=False)
    application = create_app(settings)

    async def session():
        async with maker() as db:
            yield db

    application.dependency_overrides[get_db] = session
    application.state.redis = redis
    application.state.scan_queue = queue
    application.state.image_fetcher = fetcher
    owner = await verified_account(store)
    insight_id = await keep(store, owner)
    async with browser_for(application) as http:
        await sign_in(http)
        for method, path in (
            ("POST", f"/insights/{insight_id}/publish"),
            ("DELETE", f"/insights/{insight_id}/publish"),
            ("GET", f"/public/insights/{insight_id}"),
        ):
            response = await http.request(method, path)
            assert (response.status_code, response.json()["error"]) == (404, "FEATURE_DISABLED")


async def test_a_weak_hadith_and_what_rests_on_it_stay_hidden_on_the_public_page(
    browser, other, store, flow_settings
):
    owner = await verified_account(store)
    await sign_in(browser)
    insight_id = await keep(
        store,
        owner,
        explanation=[
            {"section": "seen", "text": "قطرات على ورق نبتة.", "sources": []},
            {"section": "quran", "text": "تدعو الآية إلى النظر.", "sources": ["quran:30:50"]},
            {
                "section": "sunnah",
                "text": "يذكر الحديث الدعاء.",
                "sources": ["hadith:bukhari:1032"],
            },
            {"section": "life", "text": "تأمل ثم اعمل.", "sources": ["hadith:bukhari:1032"]},
        ],
    )
    assert (await browser.post(f"/insights/{insight_id}/publish")).status_code == 200
    # Awaiting its ruling: the verse alone, no notice to the public, the step and the parts wait.
    waiting = (await other.get(f"/public/insights/{insight_id}")).json()
    assert waiting["hadith"] is None
    assert waiting["small_step"] is None
    assert [part["section"] for part in waiting["explanation"]] == ["seen", "quran"]

    async with store() as db:
        await rule(db, "bukhari", "1032", HadithClassification.DAIF)
        await db.commit()
    weak = (await other.get(f"/public/insights/{insight_id}")).json()
    assert weak["hadith"] is None
    assert weak["quran"]["verse"]["text"] == verse_text(30, 50)
    assert [part["section"] for part in weak["explanation"]] == ["seen", "quran"]
    assert weak["small_step"] is None
