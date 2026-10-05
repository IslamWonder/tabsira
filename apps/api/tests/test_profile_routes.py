from __future__ import annotations

import logging

import pytest
from sqlalchemy import select, text

from src.models import Consent, Profile
from src.models.consent import ConsentKind
from tests.conftest import PASSPHRASE

LOGIN = {"email": "reader@example.com", "password": PASSPHRASE}
# The acceptance of the terms and the privacy policy is made at sign-up, not by these routes.
LEGAL = (ConsentKind.TERMS, ConsentKind.PRIVACY)
PRIVATE_VALUES = ("muslim", "non_muslim", "woman", "man", "25_39", "under_13")


@pytest.fixture
async def reader(web, make_user):
    """A signed-in browser."""
    user = await make_user()
    await web.post("/auth/login", json=LOGIN)
    return user


# ─── Profile ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method", ["get", "patch"])
async def test_the_profile_needs_a_session(web, method):
    kwargs = {"json": {"theme": "dark"}} if method == "patch" else {}

    assert (await getattr(web, method)("/profile", **kwargs)).status_code == 401


async def test_a_new_profile_has_every_answer_unknown_and_nothing_assumed(web, newcomer):
    response = await web.get("/profile")

    body = response.json()
    assert body.pop("updated_at")
    assert body == {
        "goals": [],
        "knowledge_level": "unknown",
        "age_range": "unknown",
        "religious_background": "unknown",
        "gender": "unknown",
        "language": "ar",
        "personalization_enabled": True,
        "memory_enabled": True,
        "photo_storage_consent": False,
        "theme": "system",
        "reduced_motion": "system",
        "sound_enabled": False,
        "questions_asked": False,
        "profile_completed_at": None,
        "consent_version": None,
    }
    assert response.headers["cache-control"] == "no-store"


async def test_a_profile_is_created_on_first_read_for_an_account_that_has_none(
    web, reader, db_session
):
    await db_session.execute(text("DELETE FROM app.profiles"))

    response = await web.get("/profile")

    assert response.status_code == 200
    assert await db_session.scalar(select(Profile)) is not None


async def test_the_motion_preference_is_saved_and_read_back(web, reader):
    await web.patch("/profile", json={"reduced_motion": "on"})

    assert (await web.get("/profile")).json()["reduced_motion"] == "on"


async def test_a_patch_changes_only_the_fields_it_sends(web, reader):
    await web.patch("/profile", json={"age_range": "25_39", "theme": "dark"})

    response = await web.patch("/profile", json={"knowledge_level": "advanced"})

    body = response.json()
    assert (body["age_range"], body["theme"], body["knowledge_level"]) == (
        "25_39",
        "dark",
        "advanced",
    )
    assert (body["gender"], body["religious_background"], body["language"]) == (
        "unknown",
        "unknown",
        "ar",
    )


async def test_an_empty_patch_changes_nothing(web, reader):
    before = (await web.get("/profile")).json()

    after = (await web.patch("/profile", json={})).json()

    assert after == before


async def test_skipping_every_question_keeps_every_answer_unknown_and_never_asks_again(web, reader):
    skipped = (await web.patch("/profile", json={"questions_asked": True})).json()

    assert (skipped["goals"], skipped["knowledge_level"], skipped["age_range"]) == (
        [],
        "unknown",
        "unknown",
    )
    assert skipped["questions_asked"] is True
    # The next insight finds the flag set and offers nothing; an answer later leaves it set.
    later = (await web.patch("/profile", json={"knowledge_level": "unknown"})).json()
    assert (later["questions_asked"], later["knowledge_level"]) == (True, "unknown")


@pytest.mark.parametrize(
    "answer",
    [
        {"goals": []},
        {"goals": ["reflection"]},
        {"knowledge_level": "general"},
        {"age_range": "unknown"},
    ],
)
async def test_answering_or_skipping_one_question_records_that_they_were_asked(web, reader, answer):
    assert (await web.get("/profile")).json()["questions_asked"] is False

    body = (await web.patch("/profile", json=answer)).json()

    assert body["questions_asked"] is True
    for field, value in answer.items():
        assert body[field] == value


async def test_a_setting_outside_the_questions_does_not_mark_them_asked(web, reader):
    body = (await web.patch("/profile", json={"theme": "dark", "gender": "woman"})).json()

    assert body["questions_asked"] is False


async def test_goals_take_several_values_including_curiosity_dropping_repeats_and_keeping_order(
    web, reader
):
    response = await web.patch(
        "/profile", json={"goals": ["curiosity", "reflection", "curiosity", "teaching"]}
    )

    assert response.json()["goals"] == ["curiosity", "reflection", "teaching"]
    assert (await web.patch("/profile", json={"goals": []})).json()["goals"] == []


async def test_every_goal_of_the_spec_is_accepted(web, reader):
    goals = [
        "discover_islam",
        "reflection",
        "learn_quran_sunnah",
        "live_values",
        "research",
        "teaching",
        "curiosity",
    ]

    assert (await web.patch("/profile", json={"goals": goals})).json()["goals"] == goals


async def test_an_answer_can_be_given_back_to_unknown(web, reader):
    await web.patch("/profile", json={"gender": "woman", "religious_background": "muslim"})

    response = await web.patch(
        "/profile", json={"gender": "unknown", "religious_background": "unknown"}
    )

    assert (response.json()["gender"], response.json()["religious_background"]) == (
        "unknown",
        "unknown",
    )


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"age_range": "30_40"}, "age_range"),
        ({"age_range": "2000-01-01"}, "age_range"),
        ({"religious_background": "atheist"}, "religious_background"),
        ({"gender": "other"}, "gender"),
        ({"knowledge_level": "expert"}, "knowledge_level"),
        ({"theme": "sepia"}, "theme"),
        ({"reduced_motion": "maybe"}, "reduced_motion"),
        ({"goals": ["wealth"]}, "goals"),
        ({"goals": "curiosity"}, "goals"),
        ({"goals": ["curiosity"] * 8}, "goals"),
        ({"language": "Arabic"}, "language"),
        ({"language": "a" * 36}, "language"),
        ({"sound_enabled": "maybe"}, "sound_enabled"),
    ],
)
async def test_a_patch_validates_every_enum_and_value(web, reader, body, field):
    response = await web.patch("/profile", json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert field in {f["loc"][1] for f in response.json()["fields"] if len(f["loc"]) > 1}


@pytest.mark.parametrize(
    "field",
    ["age_range", "gender", "theme", "reduced_motion", "goals", "language", "sound_enabled"],
)
async def test_a_null_is_refused_and_unknown_is_how_an_answer_is_cleared(web, reader, field):
    response = await web.patch("/profile", json={field: None})

    assert response.status_code == 422
    assert "null is not allowed" in response.text or "null" in response.text


@pytest.mark.parametrize(
    "field",
    [
        "photo_storage_consent",
        "personalization_enabled",
        "memory_enabled",
        "birth_date",
        "birthdate",
        "email",
        "is_admin",
        "user_id",
    ],
)
async def test_the_consent_switches_and_everything_else_are_not_patchable(web, reader, field):
    response = await web.patch("/profile", json={field: True})

    assert response.status_code == 422


async def test_a_language_tag_is_accepted(web, reader):
    for tag in ("ar", "en", "en-GB", "zh-Hant-TW"):
        assert (await web.patch("/profile", json={"language": tag})).json()["language"] == tag


async def test_one_user_never_reads_or_changes_another_profile(web, reader, make_user, account_app):
    from tests.conftest import browser_for

    await make_user("other@example.com")
    await web.patch("/profile", json={"religious_background": "muslim"})
    async with browser_for(account_app) as other:
        await other.post("/auth/login", json={"email": "other@example.com", "password": PASSPHRASE})

        theirs = await other.get("/profile")
        await other.patch("/profile", json={"theme": "dark"})

    assert theirs.json()["religious_background"] == "unknown"
    assert (await web.get("/profile")).json()["theme"] == "system"


# ─── Privacy ──────────────────────────────────────────────────────────────────


async def test_the_private_fields_never_appear_outside_the_profile_and_the_export(web, reader):
    await web.patch(
        "/profile", json={"religious_background": "muslim", "gender": "woman", "age_range": "25_39"}
    )

    for method, path, kwargs in (
        ("get", "/auth/me", {}),
        ("get", "/auth/providers", {}),
        ("post", "/auth/login", {"json": LOGIN}),
        ("get", "/health", {}),
        ("get", "/health/ready", {}),
        ("post", "/consents", {"json": {"kind": "memory", "version": "v1", "granted": True}}),
    ):
        response = await getattr(web, method)(path, **kwargs)
        for private in ("muslim", "woman", "25_39", "religious_background", "gender", "age_range"):
            assert private not in response.text, (path, private)
    own = (await web.get("/profile")).json()
    assert (own["religious_background"], own["gender"], own["age_range"]) == (
        "muslim",
        "woman",
        "25_39",
    )


async def test_only_the_profile_schemas_carry_the_private_fields(account_app):
    schemas = account_app.openapi()["components"]["schemas"]
    private = {"religious_background", "gender", "age_range"}

    carriers = {
        name for name, schema in schemas.items() if private & set(schema.get("properties", {}))
    }

    # ProfileOut: the owner's /profile and, inside AccountExport, the export.
    # ProfilePatch is a request body. A new response model that names one fails here.
    assert carriers == {"ProfileOut", "ProfilePatch"}
    export = schemas["AccountExport"]["properties"]["profile"]
    assert export["$ref"].endswith("/ProfileOut")


async def test_private_values_are_never_logged(web, reader, caplog):
    with caplog.at_level(logging.DEBUG):
        await web.patch(
            "/profile",
            json={"religious_background": "muslim", "gender": "woman", "age_range": "under_13"},
        )
        await web.get("/profile")
        await web.get("/account/export")
        await web.patch("/profile", json={"age_range": "bogus-age"})

    for private in ("muslim", "woman", "under_13", "bogus-age"):
        assert private not in caplog.text


# ─── Consents ─────────────────────────────────────────────────────────────────


async def test_consents_need_a_session(web):
    body = {"kind": "terms", "version": "v1", "granted": True}

    assert (await web.post("/consents", json=body)).status_code == 401


async def test_a_consent_is_recorded_and_the_matching_switch_follows(web, reader, db_session):
    response = await web.post(
        "/consents", json={"kind": "photo_storage", "version": "2026-10-04", "granted": True}
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["kind"], body["version"], body["granted"]) == ("photo_storage", "2026-10-04", True)
    assert body["created_at"]
    profile = (await web.get("/profile")).json()
    assert (profile["photo_storage_consent"], profile["consent_version"]) == (True, "2026-10-04")
    assert (
        len((await db_session.scalars(select(Consent).where(Consent.kind.not_in(LEGAL)))).all())
        == 1
    )


async def test_withdrawing_is_a_new_record_and_the_history_is_kept(web, reader, db_session):
    await web.post("/consents", json={"kind": "photo_storage", "version": "v1", "granted": True})
    await web.post("/consents", json={"kind": "photo_storage", "version": "v2", "granted": False})

    profile = (await web.get("/profile")).json()
    rows = (
        await db_session.scalars(
            select(Consent).where(Consent.kind.not_in(LEGAL)).order_by(Consent.version)
        )
    ).all()
    assert (profile["photo_storage_consent"], profile["consent_version"]) == (False, "v2")
    assert [(row.version, row.granted) for row in rows] == [("v1", True), ("v2", False)]


@pytest.mark.parametrize(
    ("kind", "switch", "default"),
    [("personalization", "personalization_enabled", True), ("memory", "memory_enabled", True)],
)
async def test_the_personalization_and_memory_switches_follow_their_consents(
    web, reader, kind, switch, default
):
    await web.post("/consents", json={"kind": kind, "version": "v1", "granted": False})
    assert (await web.get("/profile")).json()[switch] is False

    await web.post("/consents", json={"kind": kind, "version": "v1", "granted": True})
    assert (await web.get("/profile")).json()[switch] is True


@pytest.mark.parametrize("kind", ["terms", "privacy"])
async def test_the_terms_and_the_privacy_policy_cannot_be_accepted_through_consents(
    web, reader, db_session, kind
):
    before = (await web.get("/profile")).json()

    response = await web.post("/consents", json={"kind": kind, "version": "v3", "granted": True})

    assert response.status_code == 403
    assert response.json()["error"] == "CONSENT_NOT_ALLOWED"
    assert (await web.get("/profile")).json() == before
    rows = (await db_session.scalars(select(Consent).where(Consent.version == "v3"))).all()
    assert rows == []


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "marketing", "version": "v1", "granted": True},
        {"kind": "terms", "version": "", "granted": True},
        {"kind": "terms", "version": "has space", "granted": True},
        {"kind": "terms", "version": "x" * 33, "granted": True},
        {"kind": "terms", "version": "v1"},
        {"kind": "terms", "version": "v1", "granted": "yes please"},
        {"kind": "terms", "version": "v1", "granted": True, "user_id": "x"},
    ],
)
async def test_a_bad_consent_is_a_422(web, reader, body):
    assert (await web.post("/consents", json=body)).status_code == 422


async def test_someone_under_13_cannot_consent_to_photo_storage(web, reader, db_session):
    await web.patch("/profile", json={"age_range": "under_13"})

    response = await web.post(
        "/consents", json={"kind": "photo_storage", "version": "v1", "granted": True}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "CONSENT_NOT_ALLOWED"
    assert (await web.get("/profile")).json()["photo_storage_consent"] is False
    assert (await db_session.scalars(select(Consent).where(Consent.kind.not_in(LEGAL)))).all() == []
    # Other consents and withdrawing are unaffected.
    assert (
        await web.post("/consents", json={"kind": "memory", "version": "v1", "granted": True})
    ).status_code == 201
    assert (
        await web.post(
            "/consents", json={"kind": "photo_storage", "version": "v1", "granted": False}
        )
    ).status_code == 201


async def test_declaring_under_13_withdraws_a_photo_consent_already_given_and_records_it(
    web, reader, db_session
):
    await web.post("/consents", json={"kind": "photo_storage", "version": "v7", "granted": True})

    response = await web.patch("/profile", json={"age_range": "under_13"})

    assert response.json()["photo_storage_consent"] is False
    rows = (
        await db_session.scalars(
            select(Consent)
            .where(Consent.kind.not_in(LEGAL))
            .order_by(Consent.created_at, Consent.granted)
        )
    ).all()
    assert sorted((row.granted, row.version) for row in rows) == [(False, "v7"), (True, "v7")]


async def test_declaring_under_13_without_a_consent_records_nothing(web, reader, db_session):
    await web.patch("/profile", json={"age_range": "under_13"})

    assert (await db_session.scalars(select(Consent).where(Consent.kind.not_in(LEGAL)))).all() == []


async def test_the_withdrawal_names_an_unversioned_text_when_none_was_ever_answered(
    web, reader, db_session
):
    await db_session.execute(text("UPDATE app.profiles SET photo_storage_consent = true"))

    await web.patch("/profile", json={"age_range": "under_13"})

    (row,) = (await db_session.scalars(select(Consent).where(Consent.kind.not_in(LEGAL)))).all()
    assert (row.kind.value, row.version, row.granted) == ("photo_storage", "unversioned", False)


# ─── Completing the profile (decision 64) ─────────────────────────────────────

ANSWERS = {
    "goals": [],
    "knowledge_level": "unknown",
    "age_range": "unknown",
    "religious_background": "unknown",
    "gender": "unknown",
}


@pytest.fixture
async def newcomer(web, make_user):
    """A signed-in account whose profile was never completed."""
    user = await make_user(profile_done=False)
    await web.post("/auth/login", json=LOGIN)
    return user


async def test_a_profile_is_not_completed_until_it_says_so(web, newcomer):
    profile = (await web.get("/profile")).json()
    me = (await web.get("/auth/me")).json()

    assert profile["profile_completed_at"] is None
    assert me["profile_completed"] is False


async def test_unknown_and_no_goals_are_a_full_answer_that_completes_the_profile(web, newcomer):
    response = await web.patch("/profile", json={"complete_profile": True, **ANSWERS})

    body = response.json()
    assert response.status_code == 200
    assert body["profile_completed_at"] is not None
    assert body["questions_asked"] is True
    assert (body["religious_background"], body["gender"], body["goals"]) == ("unknown",) * 2 + ([],)
    assert (await web.get("/auth/me")).json()["profile_completed"] is True


@pytest.mark.parametrize("missing", sorted(ANSWERS))
async def test_completing_needs_an_explicit_answer_to_every_question(web, newcomer, missing):
    body = {"complete_profile": True, **{k: v for k, v in ANSWERS.items() if k != missing}}

    response = await web.patch("/profile", json=body)

    assert response.status_code == 422
    assert missing in response.text
    assert (await web.get("/profile")).json()["profile_completed_at"] is None


async def test_the_answers_of_an_earlier_patch_do_not_count_for_the_completion(web, newcomer):
    await web.patch("/profile", json=ANSWERS)

    response = await web.patch("/profile", json={"complete_profile": True})

    assert response.status_code == 422


async def test_completion_can_only_be_asked_for_never_withdrawn_and_the_date_stays(web, newcomer):
    first = (await web.patch("/profile", json={"complete_profile": True, **ANSWERS})).json()

    assert (await web.patch("/profile", json={"complete_profile": False})).status_code == 422
    assert (await web.patch("/profile", json={"complete_profile": None})).status_code == 422
    again = await web.patch(
        "/profile", json={"complete_profile": True, **ANSWERS, "gender": "woman"}
    )

    assert again.json()["gender"] == "woman"
    assert again.json()["profile_completed_at"] == first["profile_completed_at"]


async def test_the_profile_routes_stay_open_to_an_account_that_has_not_completed_it(web, newcomer):
    assert (await web.get("/profile")).status_code == 200
    assert (await web.get("/auth/me")).status_code == 200
    assert (await web.get("/account/export")).status_code == 200
    assert (await web.delete("/account")).status_code == 204
