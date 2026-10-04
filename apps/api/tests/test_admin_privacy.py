"""
Privacy of the admin area, checked across every view at once.

What a profile holds (religious background, gender, age range, goals, knowledge) is private
to its owner, and the admin has no reason to see it: no view of it exists, and none of its
columns can appear in any list, record page, form or export. The same goes for what could
replay an account: password hashes, session tokens and the second-factor secrets. These
tests walk the registered views and the rendered pages, so a view added later is held to
them too.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqladmin import ModelView

from src.models import (
    AdminSession,
    AdminTotp,
    Consent,
    ConsentKind,
    EmailToken,
    LearnerUnitState,
    LoginAttempt,
    OAuthAccount,
    OAuthState,
    Profile,
    Session,
    TokenPurpose,
)
from src.models.profile import AgeRange, Gender, Goal, KnowledgeLevel, ReligiousBackground
from tests.support_admin import (
    candidate,
    entity,
    path_domain,
    path_unit,
    path_version,
)

# Columns that must not be shown anywhere. The audit log's `ip_hash` is a keyed hash and is
# shown there on purpose; every other view omits it.
SENSITIVE_COLUMNS = {
    "religious_background",
    "gender",
    "age_range",
    "goals",
    "knowledge_level",
    "password_hash",
    "token_hash",
    "secret_encrypted",
    "recovery_hashes",
    "last_used_step",
    "guest_key",
    "code_verifier",
    "nonce",
    "state_hash",
    "binder_hash",
    "email_hash",
}
# Models that have no view: profiles and everything that can replay or identify a person.
NOT_VIEWED = {
    Profile,
    AdminSession,
    AdminTotp,
    EmailToken,
    LearnerUnitState,
    LoginAttempt,
    OAuthAccount,
    OAuthState,
}
FORBIDDEN_TEXT = (
    "$2b$",
    "muslim",
    "non_muslim",
    "woman",
    "25_39",
    "learn_quran_sunnah",
    "specialist",
    "religious",
    "age_range",
    "gender",
)


def model_views(admin_app):
    return [view for view in admin_app.state.admin.views if isinstance(view, ModelView)]


def shown_columns(view):
    """The columns a view can put on screen: its list, its record page, and a form or export if it has one."""
    shown = {*view.get_list_columns()}
    if view.can_view_details:
        shown |= {*view.get_details_columns()}
    if view.can_create or view.can_edit:
        shown |= {*view.get_form_columns()}
    if view.can_export:
        shown |= {*view.get_export_columns()}
    return shown


def test_no_view_shows_a_sensitive_column_in_its_list_its_page_its_form_or_an_export(admin_app):
    views = model_views(admin_app)
    assert len(views) >= 4

    for view in views:
        shown = shown_columns(view)
        names = {name.split(".")[-1] for name in shown}
        assert not names & SENSITIVE_COLUMNS, (view.identity, names & SENSITIVE_COLUMNS)
        # Only the audit log shows an address hash.
        if view.identity != "admin-audit-log":
            assert "ip_hash" not in names, view.identity


def test_no_view_has_one_of_the_models_that_hold_private_answers_or_credentials(admin_app):
    viewed = {view.model for view in model_views(admin_app)}

    assert not viewed & NOT_VIEWED


def test_no_view_exports_or_imports_and_none_has_a_create_or_delete_form_but_the_two_listed(
    admin_app,
):
    for view in model_views(admin_app):
        assert not view.can_export, view.identity
        assert not view.can_import, view.identity
        assert not view.can_delete, view.identity
    creatable = [view.identity for view in model_views(admin_app) if view.can_create]
    editable = sorted(view.identity for view in model_views(admin_app) if view.can_edit)

    assert creatable == []
    assert editable == ["ontology-candidate", "user"]


async def seed_everything(db_session, make_user):
    """One row of everything, with private answers and credentials where the model has them."""
    reader = await make_user("reader@example.com", display_name="Reader One")
    profile = await db_session.get(Profile, reader.id)
    profile.religious_background = ReligiousBackground.MUSLIM
    profile.gender = Gender.WOMAN
    profile.age_range = AgeRange.FROM_25_TO_39
    profile.goals = [Goal.LEARN_QURAN_SUNNAH]
    profile.knowledge_level = KnowledgeLevel.SPECIALIST
    now = datetime.now(UTC)
    db_session.add_all(
        [
            Session(
                token_hash=b"\x07" * 32,
                user_id=reader.id,
                expires_at=now + timedelta(days=1),
                last_seen_at=now,
                ip_hash="a1" * 32,
                user_agent="Firefox",
            ),
            Consent(user_id=reader.id, kind=ConsentKind.TERMS, version="v1", granted=True),
            EmailToken(
                user_id=reader.id,
                purpose=TokenPurpose.VERIFY_EMAIL,
                token_hash=b"\x08" * 32,
                email="reader@example.com",
                expires_at=now + timedelta(days=1),
            ),
            candidate("طائرة"),
            entity("E001"),
            path_version(is_active=True),
        ]
    )
    await db_session.flush()
    db_session.add(path_domain())
    await db_session.flush()
    db_session.add(path_unit())
    db_session.add(AdminTotp(user_id=reader.id, secret_encrypted="gAAAAA-secret-token"))
    await db_session.flush()
    return reader


async def test_no_page_of_any_view_shows_a_private_answer_a_hash_or_a_secret(
    admin, admin_app, make_user, db_session
):
    http, _ = admin
    await seed_everything(db_session, make_user)
    pages = 0

    for view in model_views(admin_app):
        listing = await http.get(f"/admin/{view.identity}/list")
        assert listing.status_code == 200, view.identity
        found = [listing]
        details = re.findall(rf'href="[^"]*/admin/{view.identity}/details/([^"]+)"', listing.text)
        found.extend(
            [
                await http.get(f"/admin/{view.identity}/details/{key}")
                for key in dict.fromkeys(details)
            ]
        )
        edits = re.findall(rf'href="[^"]*/admin/{view.identity}/edit/([^"]+)"', listing.text)
        found.extend(
            [await http.get(f"/admin/{view.identity}/edit/{key}") for key in dict.fromkeys(edits)]
        )
        for page in found:
            assert page.status_code == 200, (view.identity, page.url)
            lowered = page.text.lower()
            for forbidden in FORBIDDEN_TEXT:
                assert forbidden.lower() not in lowered, (view.identity, page.url, forbidden)
            for secret in ("gAAAAA-secret-token", "a1" * 32, "\\x07"):
                assert secret not in page.text, (view.identity, page.url, secret)
            pages += 1

    assert pages >= 6


@pytest.mark.parametrize("path", ["profile", "admin-session", "admin-totp", "learner-unit-state"])
async def test_the_models_that_have_no_view_have_no_page_either(admin, path):
    http, _ = admin

    for suffix in ("list", "create"):
        assert (await http.get(f"/admin/{path}/{suffix}")).status_code == 404
