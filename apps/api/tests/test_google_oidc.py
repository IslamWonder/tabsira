"""Google's side of the sign-in, against stand-ins for its token endpoint and its published keys."""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from src.services import google_oidc
from src.services.google_oidc import GoogleIdentity, GoogleOidc, OidcError
from tests.google_fake import CLIENT_ID, KID, NONCE, Google, claims, jwk_of, make_key, sign


@pytest.fixture
def google():
    return Google()


@pytest.fixture
def oidc(account_settings, google):
    return GoogleOidc(account_settings, transport=httpx.MockTransport(google.handler))


def test_the_pkce_challenge_is_the_s256_of_the_verifier_as_in_rfc_7636():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    assert google_oidc.pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_the_authorization_url_carries_pkce_state_nonce_and_the_registered_redirect(
    account_settings,
):
    url = google_oidc.authorization_url(
        account_settings, state="the-state", nonce="the-nonce", verifier="v" * 43
    )

    parts = urlsplit(url)
    query = {key: value[0] for key, value in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == google_oidc.AUTHORIZATION_ENDPOINT
    assert query == {
        "client_id": CLIENT_ID,
        "redirect_uri": "https://api.tabsira.test/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": "the-state",
        "nonce": "the-nonce",
        "code_challenge": google_oidc.pkce_challenge("v" * 43),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    assert "v" * 43 not in url


async def test_the_code_is_exchanged_with_the_verifier_and_the_client_secret(oidc, google):
    assert await oidc.exchange_code("the-code", "the-verifier") == "the-id-token"

    (sent,) = google.token_calls
    assert sent == {
        "grant_type": ["authorization_code"],
        "code": ["the-code"],
        "redirect_uri": ["https://api.tabsira.test/auth/google/callback"],
        "client_id": [CLIENT_ID],
        "client_secret": ["test-client-secret"],
        "code_verifier": ["the-verifier"],
    }


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(400, json={"error": "invalid_grant"}), "answered 400"),
        (httpx.Response(200, content=b"not json"), "sent no ID token"),
        (httpx.Response(200, json=["not", "a", "mapping"]), "sent no ID token"),
        (httpx.Response(200, json={"access_token": "only"}), "sent no ID token"),
        (httpx.Response(200, json={"id_token": ""}), "sent no ID token"),
        (httpx.Response(200, json={"id_token": 5}), "sent no ID token"),
    ],
)
async def test_a_bad_answer_from_the_token_endpoint_is_an_oidc_error(
    oidc, google, response, reason
):
    google.token_response = response

    with pytest.raises(OidcError, match=reason):
        await oidc.exchange_code("c", "v")


async def test_an_unreachable_token_endpoint_is_an_oidc_error_that_hides_the_network_text(
    oidc, google
):
    google.raise_on = google_oidc.TOKEN_ENDPOINT

    with pytest.raises(OidcError, match=r"unreachable \(ConnectError\)") as caught:
        await oidc.exchange_code("c", "v")

    assert "no route" not in str(caught.value)


async def test_a_good_id_token_gives_the_identity(oidc, google):
    token = sign(google.key)

    identity = await oidc.verify_id_token(token, nonce=NONCE)

    assert identity == GoogleIdentity(
        subject="1234567890", email="reader@example.com", name="Reader"
    )


async def test_the_issuer_may_be_written_without_the_scheme_and_the_flag_may_be_a_string(
    oidc, google
):
    token = sign(google.key, iss="accounts.google.com", email_verified="true", name=None)

    identity = await oidc.verify_id_token(token, nonce=NONCE)

    assert identity.name is None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"aud": "another-client"}, "InvalidAudienceError"),
        ({"iss": "https://evil.example"}, "InvalidIssuerError"),
        ({"exp": int(time.time()) - 600}, "ExpiredSignatureError"),
        (
            {"iat": int(time.time()) + 3600, "exp": int(time.time()) + 7200},
            "ImmatureSignatureError",
        ),
        ({"exp": None}, "MissingRequiredClaimError"),
        ({"sub": None}, "MissingRequiredClaimError"),
        ({"nonce": "someone-elses"}, "nonce does not match"),
        ({"nonce": None}, "nonce does not match"),
        ({"email_verified": False}, "not verified"),
        ({"email_verified": None}, "not verified"),
        ({"email_verified": "false"}, "not verified"),
        ({"email": None}, "no subject or e-mail"),
        ({"email": ""}, "no subject or e-mail"),
        ({"sub": ""}, "no subject or e-mail"),
    ],
)
async def test_an_id_token_is_refused_for_each_thing_that_can_be_wrong_with_it(
    oidc, google, changes, reason
):
    token = sign(google.key, **changes)

    with pytest.raises(OidcError, match=reason):
        await oidc.verify_id_token(token, nonce=NONCE)


async def test_a_token_signed_by_another_key_under_the_same_name_is_refused(oidc, google):
    forged = sign(make_key())

    with pytest.raises(OidcError, match="InvalidSignatureError"):
        await oidc.verify_id_token(forged, nonce=NONCE)


async def test_a_token_that_is_not_rs256_is_refused_before_any_key_is_fetched(oidc, google):
    hmac_token = jwt.encode(claims(), "x" * 32, algorithm="HS256", headers={"kid": KID})
    none_token = jwt.encode(claims(), None, algorithm="none", headers={"kid": KID})
    ec_token = jwt.encode(
        claims(), ec.generate_private_key(ec.SECP256R1()), algorithm="ES256", headers={"kid": KID}
    )

    for token in (hmac_token, none_token, ec_token):
        with pytest.raises(OidcError, match="not signed the way Google signs"):
            await oidc.verify_id_token(token, nonce=NONCE)

    assert google.jwks_calls == 0


async def test_a_token_without_a_key_name_or_that_is_not_a_token_is_refused(oidc, google):
    no_kid = jwt.encode(claims(), google.key, algorithm="RS256")

    with pytest.raises(OidcError, match="not signed the way Google signs"):
        await oidc.verify_id_token(no_kid, nonce=NONCE)
    with pytest.raises(OidcError, match="malformed"):
        await oidc.verify_id_token("not.a.token", nonce=NONCE)


async def test_the_keys_are_fetched_once_and_cached(oidc, google):
    for _ in range(3):
        await oidc.verify_id_token(sign(google.key), nonce=NONCE)

    assert google.jwks_calls == 1


async def test_the_keys_are_fetched_again_after_an_hour(oidc, google, moving_clock):
    await oidc.verify_id_token(sign(google.key), nonce=NONCE)

    moving_clock.advance(seconds=google_oidc.JWKS_TTL_SECONDS - 1)
    await oidc.verify_id_token(sign(google.key), nonce=NONCE)
    assert google.jwks_calls == 1

    moving_clock.advance(seconds=2)
    await oidc.verify_id_token(sign(google.key), nonce=NONCE)
    assert google.jwks_calls == 2


async def test_a_rotated_key_is_found_by_asking_again_but_not_more_than_once_a_minute(
    oidc, google, moving_clock
):
    await oidc.verify_id_token(sign(google.key), nonce=NONCE)
    new_key = make_key()
    google.keys = [jwk_of(google.key, KID), jwk_of(new_key, "key-2")]
    token = sign(new_key, kid="key-2")

    # Too soon: a forged key name must not make a request to Google every time.
    with pytest.raises(OidcError, match="unknown signing key"):
        await oidc.verify_id_token(token, nonce=NONCE)
    assert google.jwks_calls == 1

    moving_clock.advance(seconds=google_oidc.JWKS_MIN_REFETCH_SECONDS)
    identity = await oidc.verify_id_token(token, nonce=NONCE)

    assert identity.subject == "1234567890"
    assert google.jwks_calls == 2


@pytest.mark.parametrize(
    ("status", "body", "reason"),
    [
        (500, None, "signing keys unavailable"),
        (200, b"not json", "signing keys unavailable"),
        (200, json.dumps({"nokeys": []}).encode(), "signing keys unavailable"),
        (200, json.dumps({"keys": 5}).encode(), "signing keys unavailable"),
    ],
)
async def test_unusable_published_keys_are_an_oidc_error(oidc, google, status, body, reason):
    google.jwks_status, google.jwks_body = status, body or b"{}"

    with pytest.raises(OidcError, match=reason):
        await oidc.verify_id_token(sign(google.key), nonce=NONCE)


async def test_an_unreachable_key_endpoint_is_an_oidc_error(oidc, google):
    google.raise_on = google_oidc.JWKS_URI

    with pytest.raises(OidcError, match=r"unavailable \(ConnectError\)"):
        await oidc.verify_id_token(sign(google.key), nonce=NONCE)


async def test_keys_that_are_malformed_not_rsa_or_unnamed_are_skipped(oidc, google):
    elliptic = ec.generate_private_key(ec.SECP256R1())
    ec_jwk = {**ECAlgorithm.to_jwk(elliptic.public_key(), as_dict=True), "kid": "ec-key"}
    google.keys = [
        {"kty": "RSA", "kid": "broken", "n": "!!", "e": "AQAB"},
        {"nonsense": True},
        ec_jwk,
        {k: v for k, v in jwk_of(google.key, KID).items() if k != "kid"},
        jwk_of(google.key, KID),
    ]

    identity = await oidc.verify_id_token(sign(google.key), nonce=NONCE)

    assert identity.email == "reader@example.com"


async def test_the_first_use_builds_the_client_on_the_real_network_stack(account_settings):
    # No request is made: only the client the class builds when no transport is given.
    client = GoogleOidc(account_settings)._client()

    assert client.timeout == httpx.Timeout(google_oidc.HTTP_TIMEOUT_SECONDS)
    await client.aclose()
