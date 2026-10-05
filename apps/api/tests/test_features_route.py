"""GET /features: what is on, parents applied."""

from __future__ import annotations

from src.main import create_app
from tests.helpers import client_for


async def test_the_features_in_force_are_listed(make_settings):
    app = create_app(make_settings(disabled_features="social", enabled_features="social_comments"))

    async with client_for(app) as http:
        response = await http.get("/features")

    names = response.json()["features"]
    assert response.status_code == 200
    assert "chat" in names
    assert "social" not in names
    assert "social_comments" not in names
    assert "camera_anchor" not in names


async def test_requires_answers_404_for_a_feature_that_is_off_and_passes_when_on(make_settings):
    from fastapi import Depends, FastAPI

    from src.deps import requires
    from src.errors import ErrorCode, register_error_handlers
    from src.features import FeatureFlag

    probe = FastAPI()
    register_error_handlers(probe)

    @probe.get("/quiet", dependencies=[Depends(requires(FeatureFlag.CHAT))])
    async def quiet() -> dict[str, bool]:
        return {"ok": True}

    @probe.get(
        "/loud",
        dependencies=[Depends(requires(FeatureFlag.CHAT, code=ErrorCode.FEATURE_DISABLED))],
    )
    async def loud() -> dict[str, bool]:
        return {"ok": True}

    probe.state.settings = make_settings()
    async with client_for(probe) as http:
        assert (await http.get("/quiet")).status_code == 200
        probe.state.settings = make_settings(disabled_features="chat")
        absent = await http.get("/quiet")
        loud_off = await http.get("/loud")

    assert (absent.status_code, absent.json()["error"]) == (404, "NOT_FOUND")
    assert (loud_off.status_code, loud_off.json()["error"]) == (404, "FEATURE_DISABLED")
