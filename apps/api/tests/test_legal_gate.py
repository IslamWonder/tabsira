"""The server refuses a signed-in account that has not accepted the current texts."""

from __future__ import annotations

from fastapi.routing import APIRoute

from src import deps
from src.deps import CurrentUser
from src.main import create_app
from tests.test_auth_routes import LOGIN

VERSIONS = {"terms_version": "2026-10-04T20:00Z", "privacy_version": "2026-10-05T15:00Z"}

# Routes that answer an account which has not accepted: it must be able to read what it is
# asked to accept, say so, sign out, and leave (export, delete), and the open routes keep
# working. Everything else, including reading a profile, is gated by default.
EXEMPT_PATHS = {
    ("GET", "/auth/me"),
    ("POST", "/auth/legal/accept"),
    ("GET", "/account/export"),
    ("DELETE", "/account"),
    ("POST", "/support"),
    ("POST", "/consent"),
    # Taking one's own insight off public view publishes nothing.
    ("DELETE", "/insights/{insight_id}/publication"),
}


async def sign_in_unaccepted(web, make_user):
    await make_user(accepted=False)
    assert (await web.post("/auth/login", json=LOGIN)).status_code == 200


async def test_a_gated_route_answers_403_with_the_versions_until_the_texts_are_accepted(
    web, make_user
):
    await sign_in_unaccepted(web, make_user)

    for method, path in (("GET", "/profile"), ("PATCH", "/profile"), ("POST", "/consents")):
        response = await web.request(method, path, json={})
        assert response.status_code == 403, path
        body = response.json()
        assert body["error"] == "legal_acceptance_required"
        assert (body["terms_version"], body["privacy_version"]) == (
            VERSIONS["terms_version"],
            VERSIONS["privacy_version"],
        )

    await web.post("/auth/legal/accept", json=VERSIONS)
    assert (await web.get("/profile")).status_code == 200


async def test_a_new_version_gates_an_account_that_had_accepted_the_old_one(
    account_settings, make_settings, db_session, make_user
):
    from src.database import get_db
    from tests.conftest import browser_for

    await make_user()
    newer = create_app(
        make_settings(
            password_bcrypt_rounds=4,
            smtp_host="smtp.example.com",
            terms_version="2027-01-01",
        )
    )

    async def use_the_test_session():
        yield db_session

    newer.dependency_overrides[get_db] = use_the_test_session
    async with browser_for(newer) as http:
        await http.post("/auth/login", json=LOGIN)
        refused = await http.get("/profile")

    assert refused.status_code == 403
    assert refused.json()["terms_version"] == "2027-01-01"


async def test_the_exempt_routes_work_for_an_account_that_has_not_accepted(web, make_user, mailbox):
    await sign_in_unaccepted(web, make_user)

    assert (await web.get("/auth/me")).status_code == 200
    assert (await web.get("/legal")).status_code == 200
    assert (await web.get("/account/export")).status_code == 200
    support = {
        "email": "visitor@example.com",
        "topic": "bug",
        "message": "الصفحة لا تفتح عندي منذ هذا الصباح",
    }
    assert (await web.post("/support", json=support)).status_code == 202
    choice = {"policy_version": "x", "analytics": False, "behaviour": False}
    assert (await web.post("/consent", json=choice)).status_code != 403
    assert (await web.post("/auth/logout")).status_code == 204


async def test_deleting_the_account_does_not_need_the_acceptance(web, make_user):
    await sign_in_unaccepted(web, make_user)

    assert (await web.delete("/account")).status_code == 204
    assert (await web.post("/auth/login", json=LOGIN)).status_code == 401


async def test_a_route_added_later_is_gated_by_default(account_app, web, make_user):
    @account_app.get("/later-feature")
    async def later(user: CurrentUser) -> dict[str, str]:
        return {"id": str(user.id)}

    await sign_in_unaccepted(web, make_user)
    assert (await web.get("/later-feature")).status_code == 403

    await web.post("/auth/legal/accept", json=VERSIONS)
    assert (await web.get("/later-feature")).status_code == 200


def _api_routes(application):
    """Every API route, looking inside the routers the application includes."""
    for route in application.routes:
        inner = getattr(route, "original_router", None)
        for found in inner.routes if inner is not None else [route]:
            if isinstance(found, APIRoute):
                yield found


def _calls(dependant) -> set:
    found = {dependant.call}
    for sub in dependant.dependencies:
        found |= _calls(sub)
    return found


def test_only_the_listed_routes_skip_the_gate(make_settings):
    ungated = {deps.current_user_ungated, deps.optional_user_ungated}
    gated = {deps.current_user, deps.optional_user}
    application = create_app(make_settings())
    skipping = set()
    for route in _api_routes(application):
        calls = _calls(route.dependant)
        if calls & ungated and not calls & gated:
            skipping |= {(method, route.path) for method in route.methods}

    assert skipping == EXEMPT_PATHS


async def test_withdrawing_a_public_insight_does_not_need_the_acceptance_but_publishing_does(
    web, make_user
):
    await sign_in_unaccepted(web, make_user)

    assert (await web.delete("/insights/1/publication")).status_code == 404
    refused = await web.put("/insights/1/publication")
    assert (refused.status_code, refused.json()["error"]) == (403, "legal_acceptance_required")
