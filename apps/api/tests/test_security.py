from __future__ import annotations

import bcrypt
import pytest

from src import security


def test_tokens_are_long_random_and_url_safe():
    tokens = {security.new_token() for _ in range(50)}

    assert len(tokens) == 50
    assert all(
        len(token) == 43 and token.replace("-", "").replace("_", "").isalnum() for token in tokens
    )
    assert len(security.new_token_of(64)) == 86


def test_a_stored_token_hash_is_the_sha256_of_the_token_and_never_the_token():
    digest = security.hash_token("abc")

    assert digest.hex() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert security.hash_token("abc") == digest
    assert security.hash_token("abd") != digest


def test_keyed_hashes_depend_on_the_key_and_on_the_purpose():
    key = b"k" * 32

    one = security.keyed_hash(key, "ip", "203.0.113.7")

    assert len(one) == 64
    assert security.keyed_hash(key, "ip", "203.0.113.7") == one
    assert security.keyed_hash(b"j" * 32, "ip", "203.0.113.7") != one
    assert security.keyed_hash(key, "email", "203.0.113.7") != one
    assert "203.0.113.7" not in one


@pytest.mark.parametrize(
    ("host", "counted"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8:aaaa:bbbb:1:2:3:4", "2001:db8:aaaa:bbbb::/64"),
        ("2001:db8:aaaa:bbbb:ffff:ffff:ffff:ffff", "2001:db8:aaaa:bbbb::/64"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("testclient", "testclient"),
        (None, "unknown"),
        ("", "unknown"),
    ],
)
def test_the_address_a_limit_counts_is_the_v4_address_or_the_v6_64(host, counted):
    assert security.normalize_client_ip(host) == counted


@pytest.mark.parametrize(
    ("password", "problem"),
    [
        ("too short", "at least 10 characters"),
        ("ninechars", "at least 10 characters"),
        ("tencharsok", None),
        ("a" * 72, None),
        ("a" * 73, "at most 72 bytes"),
        ("\u0627" * 37, "at most 72 bytes"),
        ("\u0627" * 36, None),
        ("null\x00inside-it", "null character"),
    ],
)
def test_the_password_rules(password, problem):
    result = security.password_problem(password)

    if problem is None:
        assert result is None
    else:
        assert result is not None
        assert problem in result


def test_a_password_is_hashed_with_bcrypt_at_the_given_cost_and_checked_in_both_directions():
    hashed = security.hash_password("a good password", 4)

    assert hashed.startswith("$2b$04$")
    assert security.hash_password("a good password", 4) != hashed
    assert security.verify_password("a good password", hashed, 4) is True
    assert security.verify_password("a good passwore", hashed, 4) is False


def test_a_missing_hash_still_costs_a_full_check_against_a_decoy(monkeypatch):
    calls = []
    real = bcrypt.checkpw
    monkeypatch.setattr(
        bcrypt, "checkpw", lambda password, hashed: calls.append(hashed) or real(password, hashed)
    )

    assert security.verify_password("anything at all", None, 4) is False

    assert len(calls) == 1
    assert calls[0].startswith(b"$2b$04$")


def test_a_hash_that_is_not_bcrypt_or_a_password_that_is_too_long_never_matches():
    assert security.verify_password("a good password", "not-a-bcrypt-hash", 4) is False
    assert (
        security.verify_password("x" * 100, security.hash_password("short enough", 4), 4) is False
    )
