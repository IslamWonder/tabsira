"""The account tables, as built from the models: defaults, constraints and what must never exist."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.models import (
    AgeRange,
    AttemptKind,
    Base,
    Consent,
    ConsentKind,
    EmailToken,
    Gender,
    Goal,
    KnowledgeLevel,
    LoginAttempt,
    OAuthAccount,
    OAuthState,
    ReligiousBackground,
    Session,
    Theme,
    TokenPurpose,
    User,
)
from src.models.base import APP_SCHEMA
from src.models.profile import _GOALS_SQL
from src.services import profile_service


async def make(db_session, email="a@example.com"):
    user = User(email=email, display_name="A")
    db_session.add(user)
    await db_session.flush()
    return user


def test_no_table_has_a_birth_date_or_an_age_in_years():
    columns = {column.name for table in Base.metadata.tables.values() for column in table.columns}

    assert not {name for name in columns if "birth" in name or name in {"dob", "age"}}


def test_the_goals_are_the_seven_of_the_spec_including_curiosity():
    assert {goal.value for goal in Goal} == {
        "discover_islam",
        "reflection",
        "learn_quran_sunnah",
        "live_values",
        "research",
        "teaching",
        "curiosity",
    }
    assert "curiosity" in _GOALS_SQL


def test_the_age_ranges_and_other_answers_are_exactly_the_specified_ones():
    assert [age.value for age in AgeRange] == [
        "under_13",
        "13_17",
        "18_24",
        "25_39",
        "40_59",
        "60_plus",
        "unknown",
    ]
    assert {value.value for value in ReligiousBackground} == {"muslim", "non_muslim", "unknown"}
    assert {value.value for value in Gender} == {"man", "woman", "unknown"}
    assert {value.value for value in KnowledgeLevel} == {
        "new",
        "general",
        "advanced",
        "specialist",
        "unknown",
    }
    assert {value.value for value in Theme} == {"system", "light", "dark"}


async def test_a_new_user_is_active_not_admin_and_has_a_time_ordered_uuid(db_session):
    user = await make(db_session)

    assert user.is_active is True
    assert user.is_admin is False
    assert user.password_hash is None
    assert user.deleted_at is None
    assert user.email_verified_at is None
    assert user.created_at is not None
    assert user.id.version == 7


async def test_an_email_is_unique_whatever_its_case(db_session):
    await make(db_session, "Reader@Example.com")

    with pytest.raises(IntegrityError, match="uq_users_email_lower"):
        async with db_session.begin_nested():
            db_session.add(User(email="reader@example.COM", display_name="B"))
            await db_session.flush()


async def test_a_profile_starts_with_every_answer_unknown_and_the_switches_at_their_defaults(
    db_session,
):
    user = await make(db_session)

    profile = await profile_service.ensure_profile(db_session, user.id)

    assert profile.goals == []
    assert profile.knowledge_level is KnowledgeLevel.UNKNOWN
    assert profile.age_range is AgeRange.UNKNOWN
    assert profile.religious_background is ReligiousBackground.UNKNOWN
    assert profile.gender is Gender.UNKNOWN
    assert profile.language == "ar"
    assert profile.personalization_enabled is True
    assert profile.memory_enabled is True
    assert profile.photo_storage_consent is False
    assert profile.theme is Theme.SYSTEM
    assert profile.sound_enabled is False
    assert profile.consent_version is None
    assert profile.updated_at is not None


@pytest.mark.parametrize(
    "column", ["age_range", "religious_background", "gender", "knowledge_level", "theme"]
)
async def test_the_database_refuses_an_answer_outside_the_enum(db_session, column):
    user = await make(db_session)
    await profile_service.ensure_profile(db_session, user.id)

    with pytest.raises(IntegrityError, match=f"ck_profiles_{column}"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(f"UPDATE app.profiles SET {column} = 'bogus' WHERE user_id = :id"),  # noqa: S608
                {"id": user.id},
            )


async def test_the_database_refuses_a_goal_outside_the_list(db_session):
    user = await make(db_session)
    await profile_service.ensure_profile(db_session, user.id)

    with pytest.raises(IntegrityError, match="ck_profiles_goals_known"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE app.profiles SET goals = ARRAY['curiosity', 'wealth'] WHERE user_id = :id"
                ),
                {"id": user.id},
            )
    await db_session.execute(
        text("UPDATE app.profiles SET goals = ARRAY['curiosity', 'teaching'] WHERE user_id = :id"),
        {"id": user.id},
    )


async def test_one_profile_per_user_and_a_second_ensure_changes_nothing(db_session):
    user = await make(db_session)
    first = await profile_service.ensure_profile(db_session, user.id)
    first.language = "en"
    await db_session.flush()

    again = await profile_service.ensure_profile(db_session, user.id)

    assert again is first
    assert again.language == "en"
    with pytest.raises(IntegrityError, match="pk_profiles"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("INSERT INTO app.profiles (user_id) VALUES (:id)"), {"id": user.id}
            )


async def test_a_provider_identity_belongs_to_one_user(db_session):
    one, two = await make(db_session, "one@example.com"), await make(db_session, "two@example.com")
    db_session.add(OAuthAccount(user_id=one.id, provider="google", subject="sub-1"))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_oauth_accounts_provider_subject"):
        async with db_session.begin_nested():
            db_session.add(OAuthAccount(user_id=two.id, provider="google", subject="sub-1"))
            await db_session.flush()


async def test_a_session_token_hash_is_unique_and_exactly_32_bytes(db_session):
    from datetime import UTC, datetime

    user = await make(db_session)
    now = datetime.now(UTC)

    def session(token_hash):
        return Session(token_hash=token_hash, user_id=user.id, expires_at=now, last_seen_at=now)

    db_session.add(session(b"\x01" * 32))
    await db_session.flush()
    with pytest.raises(IntegrityError, match="uq_sessions_token_hash"):
        async with db_session.begin_nested():
            db_session.add(session(b"\x01" * 32))
            await db_session.flush()
    with pytest.raises(IntegrityError, match="ck_sessions_token_hash_length"):
        async with db_session.begin_nested():
            db_session.add(session(b"short"))
            await db_session.flush()


async def test_a_mailed_token_has_a_known_purpose_and_a_32_byte_hash(db_session):
    from datetime import UTC, datetime

    user = await make(db_session)
    token = EmailToken(
        user_id=user.id,
        purpose=TokenPurpose.PASSWORD_RESET,
        token_hash=b"\x02" * 32,
        email=user.email,
        expires_at=datetime.now(UTC),
    )
    db_session.add(token)
    await db_session.flush()

    assert token.used_at is None
    with pytest.raises(IntegrityError, match="ck_email_tokens_token_hash_length"):
        async with db_session.begin_nested():
            db_session.add(
                EmailToken(
                    user_id=user.id,
                    purpose=TokenPurpose.VERIFY_EMAIL,
                    token_hash=b"x",
                    email="a@example.com",
                    expires_at=datetime.now(UTC),
                )
            )
            await db_session.flush()
    with pytest.raises(IntegrityError, match="ck_email_tokens_purpose"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE app.email_tokens SET purpose = 'other' WHERE user_id = :id"),
                {"id": user.id},
            )


async def test_login_attempts_and_oauth_states_store_only_hashes_and_known_kinds(db_session):
    from datetime import UTC, datetime

    db_session.add(
        LoginAttempt(kind=AttemptKind.LOGIN, ip_hash="a" * 64, email_hash=None, succeeded=False)
    )
    db_session.add(
        OAuthState(
            state_hash="b" * 64,
            binder_hash="c" * 64,
            code_verifier="v" * 43,
            nonce="n",
            expires_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    assert {kind.value for kind in AttemptKind} == {
        "login",
        "signup",
        "google_start",
        "resend_verification",
        "forgot_password",
        "email_token",
    }
    with pytest.raises(IntegrityError, match="ck_login_attempts_kind"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO app.login_attempts (kind, ip_hash, succeeded) "
                    "VALUES ('other', 'x', false)"
                )
            )


async def test_a_consent_can_be_added_but_never_edited(db_session):
    user = await make(db_session)
    consent = Consent(user_id=user.id, kind=ConsentKind.PHOTO_STORAGE, version="v1", granted=True)
    db_session.add(consent)
    await db_session.flush()

    with pytest.raises(DBAPIError, match="consents are append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text("UPDATE app.consents SET granted = false"))

    # The withdrawal is a second row.
    db_session.add(
        Consent(user_id=user.id, kind=ConsentKind.PHOTO_STORAGE, version="v1", granted=False)
    )
    await db_session.flush()
    rows = (await db_session.scalars(select(Consent).order_by(Consent.created_at))).all()
    assert [row.granted for row in rows] in ([True, False], [False, True])


async def test_deleting_a_user_removes_every_row_that_belongs_to_them(db_session):
    from datetime import UTC, datetime

    user = await make(db_session)
    now = datetime.now(UTC)
    await profile_service.ensure_profile(db_session, user.id)
    db_session.add_all(
        [
            OAuthAccount(user_id=user.id, provider="google", subject="s"),
            Session(token_hash=b"\x03" * 32, user_id=user.id, expires_at=now, last_seen_at=now),
            Consent(user_id=user.id, kind=ConsentKind.TERMS, version="v1", granted=True),
            EmailToken(
                user_id=user.id,
                purpose=TokenPurpose.VERIFY_EMAIL,
                token_hash=b"\x04" * 32,
                email="a@example.com",
                expires_at=now,
            ),
        ]
    )
    await db_session.flush()

    await db_session.execute(text("DELETE FROM app.users WHERE id = :id"), {"id": user.id})

    for table in ("oauth_accounts", "sessions", "profiles", "consents", "email_tokens"):
        count = (await db_session.execute(text(f"SELECT count(*) FROM app.{table}"))).scalar_one()  # noqa: S608
        assert count == 0, table


async def test_every_foreign_key_to_users_cascades_so_deleting_an_account_leaves_nothing(engine):
    # A future table that references a user without ON DELETE CASCADE would make
    # DELETE /account fail or leave data behind; this is the guard against it.
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT conrelid::regclass::text AS child, confdeltype::text AS confdeltype
                    FROM pg_constraint
                    WHERE contype = 'f' AND confrelid = 'app.users'::regclass
                    """
                )
            )
        ).all()

    assert rows, "no table references users"
    assert {row.child.removeprefix("app.") for row in rows} == {
        "oauth_accounts",
        "sessions",
        "profiles",
        "consents",
        "email_tokens",
        "learner_unit_states",
    }
    assert {row.confdeltype for row in rows} == {"c"}


def test_every_table_lives_in_the_app_schema():
    tables = {
        # Accounts
        "users",
        "oauth_accounts",
        "sessions",
        "oauth_states",
        "profiles",
        "consents",
        "email_tokens",
        "login_attempts",
        # The world ontology and the learning path
        "ontology_entities",
        "ontology_candidates",
        "learning_path_versions",
        "learning_domains",
        "learning_units",
        "learner_unit_states",
        # The scripture store
        "quran_surahs",
        "quran_verses",
        "quran_verse_search",
        "quran_verse_history",
        "quran_annotations",
        "hadith_collections",
        "hadiths",
        "hadith_search",
        "hadith_signals",
        "hadith_rulings",
        "hadith_verification_queue",
        "scripture_sync_state",
        "scripture_audit",
    }

    assert {name.removeprefix(f"{APP_SCHEMA}.") for name in Base.metadata.tables} == tables
