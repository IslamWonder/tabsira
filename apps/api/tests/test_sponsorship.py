"""
«كفالة بصيرة», the routes (decision 60): a verified member looks after an orphaned atlas entry.

Guarded here: who may sponsor and who may not (own entry, a second sponsor, an entry that is not
orphaned, under 13, a block either way, no identity, a switch off), what a sponsorship changes
(the state, the sponsor's name beside a place that stays widened, the sign of life), the
reflection (the guard, the scripture rule, the states only its sponsor sees), and what ends it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select, update

from src import clock
from src.features import FeatureFlag
from src.geo.privacy import approximate
from src.models import (
    CommentStatus,
    MapEntry,
    MapEntryGeneralisation,
    MapEntrySponsorship,
    MapEntryStatus,
    WidenLevel,
)
from src.services import atlas_service
from tests import geo_dataset
from tests.geo_dataset import TUNIS_GOVERNORATE
from tests.helpers import any_id, switched
from tests.support_orphans import (
    NEAR_TUNIS,
    OLD,
    WHOLE,
    current_id,
    entry_row,
    fresh,
    run_job,
)
from tests.support_social import ALLOW, REJECT, REVIEW
from tests.test_atlas import _insight, _place, _published

QUOTING = "قال تعالى: «إِنَّ مَعَ ٱلۡعُسۡرِ يُسۡرًا»"


async def orphaned(db, factory, make_settings, author, **columns: Any) -> str:
    """An entry of `author` that the job has orphaned, as its public id."""
    entry = await entry_row(db, author, **columns)
    await run_job(factory, db, make_settings)
    return await current_id(db, entry.insight_id)


@pytest.fixture
async def story(db_session, factory, make_member, make_settings, world, guard):
    """An author, a would-be sponsor, a bystander, and an entry that is orphaned."""
    guard.verdict = ALLOW
    author = await make_member("author")
    sponsor = await make_member("sponsor")
    other = await make_member("other")
    entry_id = await orphaned(db_session, factory, make_settings, author)
    return author, sponsor, other, entry_id


def url(entry_id: str, tail: str = "") -> str:
    return f"/atlas/entries/{entry_id}/sponsorship{tail}"


async def openings(db) -> list[MapEntrySponsorship]:
    return list(
        await db.scalars(select(MapEntrySponsorship).execution_options(populate_existing=True))
    )


# ─── Sponsoring ───


async def test_a_member_sponsors_an_orphaned_entry_and_it_comes_back_at_the_widened_place(
    db_session, story
):
    author, sponsor, other, entry_id = story
    before = await fresh(db_session, int(entry_id))
    place = (before.public_lat, before.public_lng)
    before.last_active_at = clock.utcnow() - timedelta(days=OLD)
    await db_session.flush()

    response = await sponsor.http.put(url(entry_id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["entry_id"], body["active"], body["reflection"]) == (entry_id, True, None)
    assert body["widened_level"] == "region" and body["place"]["geoname_id"] == TUNIS_GOVERNORATE
    entry = await fresh(db_session, int(entry_id))
    assert entry.status is MapEntryStatus.PUBLISHED
    assert (
        entry.public_lat,
        entry.public_lng,
    ) == place and entry.widened_level is WidenLevel.REGION
    assert entry.last_active_at > clock.utcnow() - timedelta(minutes=1)
    assert [s.user_id for s in await openings(db_session)] == [sponsor.user.id]
    # The public page names the sponsor, never the author, and the place stays widened.
    page = (await other.http.get(f"/atlas/entries/{entry_id}")).json()
    assert page["author"] is None and page["orphaned"] is False and page["post_id"] is None
    assert page["sponsor"] == {"handle": "sponsor", "public_name": "sponsor name"}
    assert page["sponsor_reflection"] is None
    assert page["location"]["point"]["coordinates"] == [place[1], place[0]]
    assert page["location"]["widened_level"] == "region"
    # It is on the atlas again, and no longer among the orphans.
    window = (await other.http.get("/atlas/entries", params=WHOLE)).json()["features"]
    assert [(f["id"], f["properties"]["author"]) for f in window] == [(entry_id, None)]
    assert window[0]["properties"]["sponsor"]["handle"] == "sponsor"
    here = await other.http.get(f"/atlas/places/{TUNIS_GOVERNORATE}")
    assert [f["properties"]["sponsor"]["handle"] for f in here.json()["entries"]] == ["sponsor"]
    assert (await other.http.get("/atlas/orphans", params=NEAR_TUNIS)).json()["features"] == []
    # The author sees who looks after it; the sponsor finds it among their own.
    mine = (await author.http.get("/me/map-entries")).json()
    assert [(m["status"], m["sponsor"]["handle"]) for m in mine] == [("published", "sponsor")]
    listed = (await sponsor.http.get("/me/sponsorships")).json()
    assert [(item["entry_id"], item["active"]) for item in listed] == [(entry_id, True)]


async def test_a_sponsored_entry_orphaned_again_and_sponsored_by_someone_else(
    db_session, story, factory, make_settings
):
    _, sponsor, other, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    assert (await sponsor.http.delete(url(entry_id))).status_code == 204
    (await fresh(db_session, int(entry_id))).last_active_at = clock.utcnow() - timedelta(days=OLD)
    await db_session.flush()

    await run_job(factory, db_session, make_settings)

    assert (await fresh(db_session, int(entry_id))).status is MapEntryStatus.ORPHANED
    assert (await other.http.put(url(entry_id))).status_code == 200
    # The first sponsor's row went when they ended it: nothing of it is listed or kept.
    assert (await sponsor.http.get("/me/sponsorships")).json() == []
    assert len(await openings(db_session)) == 1


@pytest.mark.parametrize("who", ["author", "second", "unnamed", "unverified"])
async def test_the_refusals_of_a_sponsorship(db_session, story, make_member, who):
    author, sponsor, other, entry_id = story
    if who == "second":
        assert (await sponsor.http.put(url(entry_id))).status_code == 200
        response = await other.http.put(url(entry_id))
        assert (response.status_code, response.json()["error"]) == (409, "CONFLICT")
        assert [s.user_id for s in await openings(db_session)] == [sponsor.user.id]
        return
    member = {
        "author": author,
        "unnamed": await make_member("unnamed", identity=False),
        "unverified": await make_member("fresh", verified=False),
    }[who]

    response = await member.http.put(url(entry_id))

    expected = {"author": (409, "CONFLICT"), "unnamed": (409, "PUBLIC_IDENTITY_REQUIRED")}
    assert (response.status_code, response.json()["error"]) == expected.get(
        who, (403, "EMAIL_NOT_VERIFIED")
    )
    assert await openings(db_session) == []
    assert (await fresh(db_session, int(entry_id))).status is MapEntryStatus.ORPHANED


async def test_a_guest_a_missing_entry_and_a_withdrawn_one(db_session, story, make_member):
    author, sponsor, _, entry_id = story
    guest = await make_member(signed_in=False)

    assert (await guest.http.put(url(entry_id))).status_code == 401
    assert (await sponsor.http.put(url(any_id()))).status_code == 404
    entry = await fresh(db_session, int(entry_id))
    insight_id = entry.insight_id
    assert (await author.http.delete(f"/insights/{insight_id}/map")).status_code == 204
    gone = await sponsor.http.put(url(entry_id))
    assert (gone.status_code, gone.json()["error"]) == (410, "GONE")


async def test_an_entry_that_is_not_orphaned_cannot_be_sponsored(
    db_session, make_member, world, guard
):
    author = await make_member("author")
    sponsor = await make_member("sponsor")
    entry_id = await _published(author, await _insight(db_session, author))

    response = await sponsor.http.put(url(entry_id))

    assert (response.status_code, response.json()["error"]) == (409, "CONFLICT")
    assert await openings(db_session) == []


async def test_an_account_that_said_it_is_under_13_cannot_sponsor(db_session, story):
    _, sponsor, _, entry_id = story
    assert (await sponsor.http.patch("/profile", json={"age_range": "under_13"})).status_code == 200

    response = await sponsor.http.put(url(entry_id))

    assert (response.status_code, response.json()["error"]) == (409, "UNDER_13_CANNOT_PUBLISH")
    assert "sponsor" in response.json()["detail"]
    assert await openings(db_session) == []


@pytest.mark.parametrize("blocker", ["prober", "author"])
async def test_a_block_against_the_hidden_author_changes_no_answer(
    db_session, story, factory, make_member, make_settings, blocker
):
    """Were an answer to change with a block, the block would name the anonymous author."""
    first_author, _, _, blocked_entry = story
    second_author = await make_member("second")
    prober = await make_member("prober")
    twin = await make_member("twin")
    open_entry = await orphaned(db_session, factory, make_settings, second_author)
    one, two = (prober, first_author) if blocker == "prober" else (first_author, prober)
    assert (await one.http.put(f"/blocks/{two.handle}")).status_code == 204

    def shape(response: Any) -> tuple[int, Any]:
        body = response.json()
        if isinstance(body, dict):
            body = {key: value for key, value in body.items() if key != "id"}
        return response.status_code, body

    entry = [await prober.http.get(f"/atlas/entries/{i}") for i in (blocked_entry, open_entry)]
    assert shape(entry[0]) == shape(entry[1]) and entry[0].status_code == 200
    listed = await prober.http.get("/atlas/orphans", params=NEAR_TUNIS)
    assert {f["id"] for f in listed.json()["features"]} == {blocked_entry, open_entry}
    reports = [
        await prober.http.post(
            "/reports", json={"target_type": "map_entry", "target_id": i, "reason": "spam"}
        )
        for i in (blocked_entry, open_entry)
    ]
    assert [r.status_code for r in reports] == [201, 201]
    # Sponsoring: the prober, blocked or not, gets what an unblocked twin gets.
    mine = await prober.http.put(url(blocked_entry))
    theirs = await twin.http.put(url(open_entry))
    assert (mine.status_code, theirs.status_code) == (200, 200)
    assert [len(await openings(db_session))] == [2]


async def test_a_block_against_the_sponsor_hides_the_entry_from_the_one_who_blocked(
    db_session, story
):
    _, sponsor, other, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    visible = (await other.http.get(f"/atlas/entries/{entry_id}")).json()
    assert visible["sponsor"]["handle"] == "sponsor"
    assert (await other.http.put(f"/blocks/{sponsor.handle}")).status_code == 204

    window = (await other.http.get("/atlas/entries", params=WHOLE)).json()["features"]
    place = await other.http.get(f"/atlas/places/{TUNIS_GOVERNORATE}")
    reported = await other.http.post(
        "/reports", json={"target_type": "map_entry", "target_id": entry_id, "reason": "spam"}
    )

    assert (await other.http.get(f"/atlas/entries/{entry_id}")).status_code == 404
    assert window == [] and place.status_code == 404
    assert reported.status_code == 404
    # The sponsor, who did the blocking or was blocked, still sees their own sponsorship.
    assert len((await sponsor.http.get("/me/sponsorships")).json()) == 1


@pytest.mark.parametrize(
    "off", [[FeatureFlag.ATLAS_SPONSORSHIP], [FeatureFlag.ATLAS]], ids=["sponsoring", "atlas"]
)
async def test_every_sponsoring_route_is_a_404_while_it_or_the_atlas_is_off(
    db_session, story, account_app, account_settings, off
):
    _, sponsor, _, entry_id = story
    account_app.state.settings = switched(account_settings, off=off)

    answers = [
        (await sponsor.http.put(url(entry_id))).status_code,
        (await sponsor.http.delete(url(entry_id))).status_code,
        (
            await sponsor.http.put(url(entry_id, "/reflection"), json={"reflection": "x"})
        ).status_code,
        (await sponsor.http.get("/me/sponsorships")).status_code,
        (await sponsor.http.get("/atlas/orphans", params=NEAR_TUNIS)).status_code,
    ]

    assert answers == [404] * 5
    assert await openings(db_session) == []


# ─── The sign of life ───


async def test_publishing_placing_and_sponsoring_are_signs_of_life_and_reading_is_not(
    db_session, make_member, world, guard
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    insight_id = await _insight(db_session, author)
    assert (await _place(author, insight_id)).status_code == 200
    placed = await db_session.scalar(select(MapEntry))
    assert placed is not None
    placed.last_active_at = clock.utcnow() - timedelta(days=OLD)
    await db_session.flush()

    entry_id = await _published(author, insight_id)
    published_at = (await fresh(db_session, int(entry_id))).last_active_at
    assert published_at > clock.utcnow() - timedelta(minutes=1)

    old = clock.utcnow() - timedelta(days=OLD)
    await db_session.execute(update(MapEntry).values(last_active_at=old))
    for path in (f"/atlas/entries/{entry_id}", f"/atlas/places/{await _place_id(db_session)}"):
        assert (await guest.http.get(path)).status_code == 200
    assert (await guest.http.get("/atlas/entries", params=WHOLE)).status_code == 200
    assert (await fresh(db_session, int(entry_id))).last_active_at == old

    assert (await _place(author, insight_id, latitude=36.8, longitude=10.18)).status_code == 200
    assert (await fresh(db_session, int(entry_id))).last_active_at > old


async def _place_id(db) -> int:
    entry = await db.scalar(select(MapEntry))
    assert entry is not None and entry.place_geoname_id is not None
    return entry.place_geoname_id


# ─── Ending ───


async def test_the_sponsor_ends_it_and_the_reflection_goes_with_it(db_session, story):
    _, sponsor, other, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    assert (
        await sponsor.http.put(url(entry_id, "/reflection"), json={"reflection": "نفعني هذا"})
    ).status_code == 200

    assert (await other.http.delete(url(entry_id))).status_code == 404
    assert (await sponsor.http.delete(url(entry_id))).status_code == 204

    assert (await sponsor.http.delete(url(entry_id))).status_code == 404
    entry = await fresh(db_session, int(entry_id))
    assert entry.status is MapEntryStatus.PUBLISHED
    page = (await other.http.get(f"/atlas/entries/{entry_id}")).json()
    assert page["sponsor"] is None and page["sponsor_reflection"] is None
    # The row, and the words with it, are gone: nothing of an ended sponsorship is kept or listed.
    assert await openings(db_session) == []
    assert (await sponsor.http.get("/me/sponsorships")).json() == []
    assert (await sponsor.http.get("/account/export")).json()["sponsorships"] == []


async def test_the_author_cannot_place_a_sponsored_entry_again(db_session, story):
    author, sponsor, _, entry_id = story
    entry = await fresh(db_session, int(entry_id))
    insight_id = entry.insight_id
    # The author has a private point for it, as every placed entry does.
    assert (await sponsor.http.put(url(entry_id))).status_code == 200

    refused = await _place(author, insight_id)

    assert (refused.status_code, refused.json()["error"]) == (409, "CONFLICT")
    assert (await fresh(db_session, int(entry_id))).status is MapEntryStatus.PUBLISHED


async def test_the_author_withdrawing_the_entry_ends_the_sponsorship_and_erases_the_rest(
    db_session, make_member, factory, make_settings, world, guard
):
    guard.verdict = ALLOW
    author = await make_member("author")
    sponsor = await make_member("sponsor")
    insight_id = await _insight(db_session, author)
    first = await _published(author, insight_id)
    (await fresh(db_session, int(first))).last_active_at = clock.utcnow() - timedelta(days=OLD)
    await db_session.flush()
    await run_job(factory, db_session, make_settings)
    published = await current_id(db_session, insight_id)
    assert (await sponsor.http.put(url(published))).status_code == 200
    assert (
        await sponsor.http.put(url(published, "/reflection"), json={"reflection": "كلمة"})
    ).status_code == 200

    assert (await author.http.delete(f"/insights/{insight_id}/map")).status_code == 204

    assert await openings(db_session) == []
    assert (await sponsor.http.get("/me/sponsorships")).json() == []
    assert (await sponsor.http.get(f"/atlas/entries/{published}")).status_code == 410
    assert list(await db_session.scalars(select(MapEntryGeneralisation))) == []


async def test_closing_the_sponsor_s_account_removes_the_sponsorship_and_nothing_else(
    db_session, story
):
    _, sponsor, other, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    assert (
        await sponsor.http.put(url(entry_id, "/reflection"), json={"reflection": "كلمة"})
    ).status_code == 200

    assert (await sponsor.http.delete("/account")).status_code == 204

    assert list(await db_session.scalars(select(MapEntrySponsorship))) == []
    page = (await other.http.get(f"/atlas/entries/{entry_id}")).json()
    assert page["sponsor"] is None and page["author"] is None
    assert (await fresh(db_session, int(entry_id))).status is MapEntryStatus.PUBLISHED


async def test_the_export_holds_the_sponsorships_of_the_account(db_session, story):
    _, sponsor, _, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    assert (
        await sponsor.http.put(url(entry_id, "/reflection"), json={"reflection": "كلمة"})
    ).status_code == 200

    exported = (await sponsor.http.get("/account/export")).json()

    assert [(s["entry_id"], s["reflection"]) for s in exported["sponsorships"]] == [
        (entry_id, "كلمة")
    ]


# ─── The reflection ───


async def reflect(member, entry_id: str, text: str = "نفعني هذا المكان") -> Any:
    return await member.http.put(url(entry_id, "/reflection"), json={"reflection": text})


async def test_an_allowed_reflection_is_published_under_the_entry_and_replaced_by_the_next(
    db_session, story
):
    _, sponsor, other, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    (await fresh(db_session, int(entry_id))).last_active_at = clock.utcnow() - timedelta(days=OLD)
    await db_session.flush()

    first = await reflect(sponsor, entry_id)

    assert first.status_code == 200, first.text
    assert (first.json()["reflection"], first.json()["reflection_status"]) == (
        "نفعني هذا المكان",
        "published",
    )
    assert first.json()["reflection_message"] is None
    assert (await other.http.get(f"/atlas/entries/{entry_id}")).json()[
        "sponsor_reflection"
    ] == "نفعني هذا المكان"
    assert (await fresh(db_session, int(entry_id))).last_active_at > clock.utcnow() - timedelta(
        minutes=1
    )
    second = await reflect(sponsor, entry_id, "كلمة أخرى")
    assert second.json()["reflection"] == "كلمة أخرى"
    assert len(await openings(db_session)) == 1
    assert (await other.http.get(f"/atlas/entries/{entry_id}")).json()[
        "sponsor_reflection"
    ] == "كلمة أخرى"


@pytest.mark.parametrize(("verdict", "status"), [(REVIEW, "pending_review"), (REJECT, "rejected")])
async def test_a_held_or_refused_reflection_is_seen_by_its_sponsor_alone(
    db_session, story, guard, verdict, status
):
    _, sponsor, other, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    guard.verdict = verdict

    response = await reflect(sponsor, entry_id)

    assert response.status_code == 200
    assert response.json()["reflection_status"] == status
    assert response.json()["reflection_message"]
    assert guard.texts == ["نفعني هذا المكان"]
    page = (await other.http.get(f"/atlas/entries/{entry_id}")).json()
    assert page["sponsor"]["handle"] == "sponsor" and page["sponsor_reflection"] is None
    mine = (await sponsor.http.get("/me/sponsorships")).json()
    assert [(i["reflection"], i["reflection_status"]) for i in mine] == [
        ("نفعني هذا المكان", status)
    ]
    stored = (await openings(db_session))[0]
    assert stored.reflection_status in {CommentStatus.PENDING_REVIEW, CommentStatus.REJECTED}


async def test_words_that_read_like_scripture_are_refused_before_the_guard_or_the_store(
    db_session, story, guard
):
    _, sponsor, _, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200

    response = await reflect(sponsor, entry_id, QUOTING)

    assert (response.status_code, response.json()["error"]) == (422, "VALIDATION_ERROR")
    assert guard.texts == []
    assert (await openings(db_session))[0].reflection is None


@pytest.mark.parametrize("text", ["", "   ", "x" * 1001, "a" + chr(0x202E) + "b"])
async def test_an_empty_too_long_or_disguised_reflection_is_refused(db_session, story, text):
    _, sponsor, _, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200

    assert (await reflect(sponsor, entry_id, text)).status_code == 422
    assert (await openings(db_session))[0].reflection is None


async def test_only_the_sponsor_of_an_open_sponsorship_can_write(db_session, story):
    _, sponsor, other, entry_id = story
    assert (await reflect(sponsor, entry_id)).status_code == 404
    assert (await sponsor.http.put(url(entry_id))).status_code == 200

    assert (await reflect(other, entry_id)).status_code == 404
    assert (await reflect(sponsor, any_id())).status_code == 404
    assert (await sponsor.http.put(url(entry_id, "/reflection"), json={})).status_code == 422
    assert (await sponsor.http.delete(url(entry_id))).status_code == 204
    assert (await reflect(sponsor, entry_id)).status_code == 404


async def test_a_reflection_is_refused_while_a_moderator_holds_the_entry(db_session, story):
    _, sponsor, _, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    (await fresh(db_session, int(entry_id))).status = MapEntryStatus.PENDING_REVIEW
    await db_session.flush()

    response = await reflect(sponsor, entry_id)

    # A held entry is not on the atlas: it is as absent for its sponsor as for anyone.
    assert (response.status_code, response.json()["error"]) == (404, "NOT_FOUND")


async def test_a_sponsorship_on_an_entry_that_is_not_published_takes_no_reflection(
    db_session, story, guard
):
    _, sponsor, _, entry_id = story
    # A state the routes never make (a sponsored entry is published); the check holds anyway.
    db_session.add(MapEntrySponsorship(entry_id=int(entry_id), user_id=sponsor.user.id))
    await db_session.flush()

    response = await reflect(sponsor, entry_id)

    assert (response.status_code, response.json()["error"]) == (409, "CONFLICT")
    assert guard.texts == []


@pytest.mark.parametrize("change", ["replaced", "deleted"])
async def test_a_reflection_changed_while_the_guard_judged_it_is_not_settled(
    db_session, story, guard, change
):
    _, sponsor, _, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200

    async def meanwhile() -> None:
        if change == "deleted":
            await db_session.execute(MapEntrySponsorship.__table__.delete())
        else:
            await db_session.execute(update(MapEntrySponsorship).values(reflection="غيرتُ رأيي"))

    guard.during = meanwhile

    response = await reflect(sponsor, entry_id)

    assert (response.status_code, response.json()["error"]) == (409, "CONFLICT")


# ─── Orphans near a point ───


async def test_orphans_near_a_point_are_listed_at_their_widened_place_only(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member("author")
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    near = await orphaned(db_session, factory, make_settings, author)
    mecca = await orphaned(
        db_session,
        factory,
        make_settings,
        author,
        place=geo_dataset.MECCA_CITY,
        lat=21.42,
        lng=39.82,
        country_iso2="SA",
    )
    published = await entry_row(db_session, author, age_days=1)
    del published

    around_tunis = await guest.http.get("/atlas/orphans", params=NEAR_TUNIS)
    around_mecca = await guest.http.get("/atlas/orphans", params={"lat": 21.4, "lng": 39.8})

    assert around_tunis.status_code == 200
    assert around_tunis.headers["cache-control"] == "no-store"
    assert [f["id"] for f in around_tunis.json()["features"]] == [near]
    assert [f["id"] for f in around_mecca.json()["features"]] == [mecca]
    feature = around_tunis.json()["features"][0]
    assert feature["geometry"]["coordinates"] == [10.2, 36.8]
    assert feature["properties"]["author"] is None
    assert feature["properties"]["orphaned"] is True and feature["properties"]["sponsor"] is None
    assert feature["properties"]["precision_label"] == "على مستوى المنطقة"
    assert feature["properties"]["place"]["label"] == "ولاية تونس"
    assert around_tunis.json()["next_cursor"] is None
    # Near is the widened area the position lies in, or a public point within the radius.
    paris = await guest.http.get("/atlas/orphans", params={"lat": 48.85, "lng": 2.35})
    nowhere = await guest.http.get("/atlas/orphans", params={"lat": 0.0, "lng": 0.0})
    assert paris.json()["features"] == [] and nowhere.json()["features"] == []
    outside = {"lat": 36.0, "lng": 10.0}
    short = await guest.http.get("/atlas/orphans", params={**outside, "radius": 10000})
    wide = await guest.http.get("/atlas/orphans", params={**outside, "radius": 300000})
    assert short.json()["features"] == []
    assert [f["id"] for f in wide.json()["features"]] == [near]
    # A block changes nothing: the author is anonymous, and a missing entry would name them.
    assert (await reader.http.put("/blocks/author")).status_code == 204
    kept = await reader.http.get("/atlas/orphans", params=NEAR_TUNIS)
    assert [f["id"] for f in kept.json()["features"]] == [near]


async def test_the_position_is_snapped_to_a_grid_before_anything_is_asked(
    db_session, factory, make_member, make_settings, world, monkeypatch
):
    guest = await make_member(signed_in=False)
    asked: list[tuple[float, float]] = []
    real = atlas_service._near

    def spy(lat: float, lng: float, radius_m: float):
        asked.append((lat, lng))
        return real(lat, lng, radius_m)

    monkeypatch.setattr(atlas_service, "_near", spy)

    response = await guest.http.get("/atlas/orphans", params={"lat": 36.81234, "lng": 10.17777})

    assert response.status_code == 200
    snapped = approximate(36.81234, 10.17777, atlas_service.ORPHAN_QUERY_CELL_M)
    assert asked == [(snapped.lat, snapped.lng)] and asked != [(36.81234, 10.17777)]
    # A position anywhere in the same cell asks the same thing.
    again = await guest.http.get(
        "/atlas/orphans", params={"lat": snapped.lat + 0.0001, "lng": snapped.lng - 0.0001}
    )
    assert again.status_code == 200 and asked[1] == asked[0]


async def test_orphans_page_with_a_cursor_newest_first(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    ids = [await orphaned(db_session, factory, make_settings, author) for _ in range(3)]

    first = (await guest.http.get("/atlas/orphans", params={**NEAR_TUNIS, "limit": 2})).json()
    second = (
        await guest.http.get(
            "/atlas/orphans", params={**NEAR_TUNIS, "limit": 2, "cursor": first["next_cursor"]}
        )
    ).json()

    assert [f["id"] for f in first["features"]] == [ids[2], ids[1]]
    assert first["next_cursor"] is not None
    assert [f["id"] for f in second["features"]] == [ids[0]]
    assert second["next_cursor"] is None
    bad = await guest.http.get("/atlas/orphans", params={**NEAR_TUNIS, "cursor": "nope"})
    assert bad.status_code == 400


async def test_orphans_are_found_across_the_antimeridian(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    west = await orphaned(
        db_session,
        factory,
        make_settings,
        author,
        place=geo_dataset.WESTERN_EDGE,
        lat=51.0,
        lng=-179.9,
        country_iso2=None,
    )

    found = await guest.http.get(
        "/atlas/orphans", params={"lat": 51.0, "lng": 179.95, "radius": 100000}
    )
    missed = await guest.http.get(
        "/atlas/orphans", params={"lat": 51.0, "lng": 100.0, "radius": 100000}
    )

    assert [f["id"] for f in found.json()["features"]] == [west]
    assert missed.json()["features"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 91, "lng": 0},
        {"lat": 0, "lng": 181},
        {"lat": 0, "lng": 0, "radius": 10},
        {"lat": 0, "lng": 0, "radius": 10_000_000},
        {"lat": 0, "lng": 0, "limit": 0},
        {"lat": 0},
        {},
    ],
)
async def test_orphans_refuse_a_bad_position_radius_or_limit(make_member, world, params):
    guest = await make_member(signed_in=False)

    assert (await guest.http.get("/atlas/orphans", params=params)).status_code == 422


async def test_an_orphaned_entry_can_be_reported_by_others_but_not_by_its_author(db_session, story):
    author, _, other, entry_id = story
    report = {"target_type": "map_entry", "target_id": entry_id, "reason": "wrong_place"}

    assert (await other.http.post("/reports", json=report)).status_code == 201
    assert (await author.http.post("/reports", json=report)).status_code == 400


async def test_the_export_holds_the_sponsorship_of_an_entry_a_moderator_holds(db_session, story):
    _, sponsor, _, entry_id = story
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    assert (await reflect(sponsor, entry_id)).status_code == 200
    (await fresh(db_session, int(entry_id))).status = MapEntryStatus.PENDING_REVIEW
    await db_session.flush()

    listed = (await sponsor.http.get("/me/sponsorships")).json()
    exported = (await sponsor.http.get("/account/export")).json()["sponsorships"]

    # The app lists nothing of a held entry; the sponsor's own words are still theirs to export.
    assert listed == []
    assert [(item["entry_id"], item["reflection"]) for item in exported] == [
        (entry_id, "نفعني هذا المكان")
    ]


def test_the_published_description_of_sponsoring_does_not_promise_an_author_block_404(account_app):
    operation = account_app.openapi()["paths"]["/atlas/entries/{entry_id}/sponsorship"]["put"]

    assert "between them and its author" not in operation["description"]
    assert "anonymous author changes nothing" in operation["description"]
