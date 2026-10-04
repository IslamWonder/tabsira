"""
The admin second factor: the secret at rest, the code with a fixed clock, replay and recovery.

The RFC 6238 test vectors pin the code itself: the secret `12345678901234567890` gives
94287082 at the epoch second 59 (eight digits in the RFC, six here: 287082).
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import UTC, datetime

import pyotp
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from src.models import AdminTotp
from src.services import admin_totp_service as service

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()
KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


@pytest.fixture
def settings(make_settings):
    return make_settings(admin_totp_encryption_key=KEY_A)


@pytest.fixture
async def admin(make_user):
    return await make_user(is_admin=True)


def at(moving_clock, timestamp: int) -> None:
    moving_clock.now = datetime.fromtimestamp(timestamp, UTC)


def code_at(secret: str, timestamp: int) -> str:
    return pyotp.TOTP(secret).at(timestamp)


async def enroll(db, settings, admin, moving_clock, timestamp=1_000_000_000):
    """Enrol `admin` at `timestamp`; return the secret, the recovery codes and the timestamp."""
    at(moving_clock, timestamp)
    secret = await service.start_enrollment(db, settings, admin)
    codes = await service.confirm_enrollment(db, settings, admin, code_at(secret, timestamp))
    assert codes is not None
    return secret, codes


def test_the_codes_follow_the_rfc_6238_vectors(moving_clock):
    for timestamp, expected in ((59, "287082"), (1111111109, "081804"), (2000000000, "279037")):
        at(moving_clock, timestamp)
        assert service._matching_step(RFC_SECRET, expected) == timestamp // 30
    at(moving_clock, 59)
    assert service._matching_step(RFC_SECRET, "287083") is None


def test_the_secret_is_encrypted_at_rest_and_opens_with_any_configured_key(make_settings):
    old = make_settings(admin_totp_encryption_key=KEY_A)
    rotated = make_settings(admin_totp_encryption_key=f"{KEY_B},{KEY_A}")
    new_only = make_settings(admin_totp_encryption_key=KEY_B)

    token = service.encrypt_secret(old, RFC_SECRET)

    assert RFC_SECRET not in token
    assert token != service.encrypt_secret(old, RFC_SECRET)
    assert service.decrypt_secret(old, token) == RFC_SECRET
    # After a rotation the old key still opens it, and the new key encrypts from now on.
    assert service.decrypt_secret(rotated, token) == RFC_SECRET
    assert (
        service.decrypt_secret(new_only, service.encrypt_secret(rotated, RFC_SECRET)) == RFC_SECRET
    )


def test_a_secret_no_configured_key_opens_is_none_and_the_log_says_why(make_settings, caplog):
    token = service.encrypt_secret(make_settings(admin_totp_encryption_key=KEY_A), RFC_SECRET)

    with caplog.at_level(logging.ERROR, logger="tabsira.admin.totp"):
        assert service.decrypt_secret(make_settings(admin_totp_encryption_key=KEY_B), token) is None

    assert "ADMIN_TOTP_ENCRYPTION_KEY" in caplog.text
    assert RFC_SECRET not in caplog.text


def test_recovery_codes_are_sixteen_hex_digits_in_groups_and_all_different():
    codes = service.new_recovery_codes()

    assert len(codes) == len(set(codes)) == service.RECOVERY_CODE_COUNT
    assert all(re.fullmatch(r"[0-9a-f]{4}(-[0-9a-f]{4}){3}", code) for code in codes)


def test_a_recovery_code_hashes_the_same_whatever_its_case_or_dashes(settings, make_settings):
    code = "ABCD-ef01-2345-6789"

    hashed = service.hash_recovery_code(settings, code)

    assert hashed == service.hash_recovery_code(settings, "abcdef0123456789")
    assert hashed == service.hash_recovery_code(settings, " abcd ef01 2345 6789 ")
    assert "abcdef01" not in hashed
    assert hashed != service.hash_recovery_code(make_settings(hash_secret="x" * 40), code)


def test_the_provisioning_uri_names_the_issuer_and_the_account():
    from src.models import User

    uri = service.provisioning_uri(User(email="a@example.com", display_name="A"), RFC_SECRET)

    assert uri.startswith("otpauth://totp/")
    assert "a%40example.com" in uri
    assert "issuer=TABSIRA%20admin" in uri
    assert f"secret={RFC_SECRET}" in uri


def test_the_secret_is_shown_in_groups_of_four():
    assert service.readable("ABCDEFGHIJ") == "ABCD EFGH IJ"


async def test_starting_an_enrolment_stores_an_encrypted_pending_secret(
    db_session, settings, admin
):
    secret = await service.start_enrollment(db_session, settings, admin)

    row = await service.get(db_session, admin.id)
    assert row is not None
    assert service.is_enabled(row) is False
    assert secret not in row.secret_encrypted
    assert service.decrypt_secret(settings, row.secret_encrypted) == secret
    assert len(secret) == 32
    assert row.recovery_hashes == []
    # Starting again replaces the pending secret.
    again = await service.start_enrollment(db_session, settings, admin)
    assert again != secret
    assert len((await db_session.scalars(select(AdminTotp))).all()) == 1


async def test_a_wrong_first_code_leaves_the_enrolment_pending(
    db_session, settings, admin, moving_clock
):
    at(moving_clock, 1_000_000_000)
    secret = await service.start_enrollment(db_session, settings, admin)

    assert await service.confirm_enrollment(db_session, settings, admin, "000000") is None
    assert await service.confirm_enrollment(db_session, settings, admin, "not-a-code") is None

    row = await service.get(db_session, admin.id)
    assert row is not None
    assert row.enabled_at is None
    # The same secret then still confirms.
    codes = await service.confirm_enrollment(
        db_session, settings, admin, code_at(secret, 1_000_000_000)
    )
    assert codes is not None


async def test_a_right_first_code_enables_the_factor_and_shows_the_recovery_codes_once(
    db_session, settings, admin, moving_clock
):
    secret, codes = await enroll(db_session, settings, admin, moving_clock)

    row = await service.get(db_session, admin.id)
    assert row is not None
    assert service.is_enabled(row) is True
    assert row.enabled_at == moving_clock.now
    assert row.last_used_step == 1_000_000_000 // 30
    assert len(codes) == service.RECOVERY_CODE_COUNT
    # Only keyed hashes are stored: no code appears in the table.
    assert len(row.recovery_hashes) == service.RECOVERY_CODE_COUNT
    assert not set(codes) & set(row.recovery_hashes)
    assert row.recovery_hashes == [service.hash_recovery_code(settings, code) for code in codes]
    # Confirming again changes nothing.
    assert (
        await service.confirm_enrollment(
            db_session, settings, admin, code_at(secret, 1_000_000_000 + 30)
        )
        is None
    )


async def test_there_is_nothing_to_confirm_without_a_started_enrolment(db_session, settings, admin):
    assert await service.confirm_enrollment(db_session, settings, admin, "123456") is None


async def test_a_secret_the_keys_cannot_open_confirms_nothing(
    db_session, settings, admin, make_settings
):
    await service.start_enrollment(db_session, settings, admin)
    other_keys = make_settings(admin_totp_encryption_key=KEY_B)

    assert await service.confirm_enrollment(db_session, other_keys, admin, "123456") is None


async def test_a_code_works_once_and_the_next_step_works_again(
    db_session, settings, admin, moving_clock
):
    secret, _ = await enroll(db_session, settings, admin, moving_clock)

    at(moving_clock, 1_000_000_000 + 60)
    code = code_at(secret, 1_000_000_000 + 60)
    assert await service.verify(db_session, settings, admin, code) is True
    # The same code, still inside its window, is refused.
    assert await service.verify(db_session, settings, admin, code) is False
    # So is the one before it, which is below the last used step.
    assert (
        await service.verify(db_session, settings, admin, code_at(secret, 1_000_000_000 + 30))
        is False
    )
    # The next step's code is a new code.
    at(moving_clock, 1_000_000_000 + 90)
    assert (
        await service.verify(db_session, settings, admin, code_at(secret, 1_000_000_000 + 90))
        is True
    )


async def test_a_phone_clock_one_step_ahead_or_behind_is_tolerated_but_two_are_not(
    db_session, settings, admin, moving_clock
):
    secret, _ = await enroll(db_session, settings, admin, moving_clock)
    now = 1_000_000_000 + 600
    at(moving_clock, now)

    assert await service.verify(db_session, settings, admin, code_at(secret, now + 2 * 30)) is False
    assert await service.verify(db_session, settings, admin, code_at(secret, now - 2 * 30)) is False
    assert await service.verify(db_session, settings, admin, code_at(secret, now + 30)) is True


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "12 456", "١٢٣٤٥٦"])
async def test_a_malformed_code_is_refused_without_touching_the_recovery_codes(
    db_session, settings, admin, moving_clock, bad
):
    await enroll(db_session, settings, admin, moving_clock)

    assert await service.verify(db_session, settings, admin, bad) is False

    row = await service.get(db_session, admin.id)
    assert row is not None
    assert len(row.recovery_hashes) == service.RECOVERY_CODE_COUNT


async def test_a_valid_authenticator_code_never_burns_a_recovery_code(
    db_session, settings, admin, moving_clock
):
    secret, _ = await enroll(db_session, settings, admin, moving_clock)
    at(moving_clock, 1_000_000_000 + 60)

    assert await service.verify(db_session, settings, admin, code_at(secret, 1_000_000_000 + 60))

    row = await service.get(db_session, admin.id)
    assert row is not None
    assert len(row.recovery_hashes) == service.RECOVERY_CODE_COUNT


async def test_a_recovery_code_works_once_in_any_case_and_a_wrong_one_never(
    db_session, settings, admin, moving_clock
):
    _, codes = await enroll(db_session, settings, admin, moving_clock)

    assert await service.verify(db_session, settings, admin, "0000-0000-0000-0000") is False
    assert await service.verify(db_session, settings, admin, codes[0].upper()) is True
    assert await service.verify(db_session, settings, admin, codes[0]) is False
    assert await service.verify(db_session, settings, admin, codes[1].replace("-", " ")) is True

    row = await service.get(db_session, admin.id)
    assert row is not None
    assert len(row.recovery_hashes) == service.RECOVERY_CODE_COUNT - 2


async def test_with_a_lost_key_only_a_recovery_code_still_gets_in(
    db_session, settings, admin, moving_clock, make_settings
):
    secret, codes = await enroll(db_session, settings, admin, moving_clock)
    lost_key = make_settings(admin_totp_encryption_key=KEY_B)
    at(moving_clock, 1_000_000_000 + 60)

    assert (
        await service.verify(db_session, lost_key, admin, code_at(secret, 1_000_000_000 + 60))
        is False
    )
    assert await service.verify(db_session, lost_key, admin, codes[0]) is True


async def test_nothing_verifies_for_an_admin_who_is_not_enrolled_or_only_started(
    db_session, settings, admin, moving_clock
):
    at(moving_clock, 1_000_000_000)
    assert await service.verify(db_session, settings, admin, "123456") is False

    secret = await service.start_enrollment(db_session, settings, admin)
    assert (
        await service.verify(db_session, settings, admin, code_at(secret, 1_000_000_000)) is False
    )


async def test_disabling_removes_the_secret_and_the_codes(
    db_session, settings, admin, moving_clock
):
    await enroll(db_session, settings, admin, moving_clock)

    assert await service.disable(db_session, admin.id) is True
    assert await service.get(db_session, admin.id) is None
    assert await service.disable(db_session, admin.id) is False
