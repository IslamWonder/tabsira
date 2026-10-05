"""Comments have a switch of their own, off by default (decision 63)."""

from __future__ import annotations

import pytest

from src.features import FeatureFlag
from tests.helpers import any_id, switched
from tests.support_social import publish_post

ROUTES = (
    ("GET", "/posts/{post}/comments"),
    ("POST", "/posts/{post}/comments"),
    ("DELETE", "/posts/{post}/comments/{comment}"),
)


async def answers(member, post_id: str) -> list[int]:
    codes = []
    for method, template in ROUTES:
        path = template.format(post=post_id, comment=any_id())
        codes.append((await member.http.request(method, path, json={"body": "تعليق"})).status_code)
    return codes


async def test_every_comment_route_is_a_404_by_default(make_member, make_insight):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)

    assert await answers(reader, post_id) == [404, 404, 404]
    # The post itself is untouched by the comment switch.
    assert (await reader.http.get(f"/posts/{post_id}")).status_code == 200


async def test_comments_open_when_enabled_and_follow_the_network_switch(
    make_member, make_insight, account_app, account_settings
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)

    account_app.state.settings = switched(account_settings, on=[FeatureFlag.SOCIAL_COMMENTS])
    assert (await reader.http.get(f"/posts/{post_id}/comments")).status_code == 200

    account_app.state.settings = switched(
        account_settings, on=[FeatureFlag.SOCIAL_COMMENTS], off=[FeatureFlag.SOCIAL]
    )
    assert (await reader.http.get(f"/posts/{post_id}/comments")).status_code == 404


@pytest.mark.parametrize("target_type", ["comment"])
async def test_a_comment_cannot_be_reported_while_comments_are_off(
    make_member, make_insight, target_type
):
    author = await make_member("author")
    reader = await make_member("reader")
    await publish_post(author, make_insight)

    response = await reader.http.post(
        "/reports",
        json={"target_type": target_type, "target_id": str(any_id()), "reason": "spam"},
    )

    assert response.status_code == 404
