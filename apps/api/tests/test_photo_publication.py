"""
The public copy of a kept photo exists exactly while a post or a map entry shows it (v2 §19).

Made when the owner publishes with the photo chosen and the rules still allow it, deleted when
the last publication showing it is withdrawn or removed; no response ever carries a key. Its
address (`photo_url`) is given only by a published public post or a published entry that shows
it, and the local `/media` route serves the public prefix alone.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.models import (
    Insight,
    InsightPublication,
    MapEntry,
    Post,
    PostStatus,
    Report,
    ReportReason,
    ReportTarget,
)
from src.owner import Owner
from src.services import moderation_service, photo_service
from src.services.insight_table_source import InsightTableSource
from src.storage.base import (
    ObjectNotFoundError,
    Storage,
    StorageUnavailableError,
    new_private_key,
    new_public_key,
)
from src.storage.local import LocalStorage
from src.storage.photos import PhotoStore
from tests import geo_dataset as world_data
from tests.helpers import any_id
from tests.scans.builders import insight_row, scan_row
from tests.support_images import jpeg_of, pixels
from tests.support_social import ALLOW, Member, new_comment, new_post

MODERATOR_ID = __import__("uuid").uuid4()
EXACT = {
    "latitude": 36.806512,
    "longitude": 10.181534,
    "accuracy_m": 12,
    "source": "device_capture",
}
EVIDENCE: dict[str, Any] = {
    "quran_surah": 112,
    "quran_ayah": 1,
    "hadith_collection": "bukhari",
    "hadith_number": "1",
    "explanation": [{"section": "seen", "text": "قطرات على ورق نبتة.", "sources": []}],
    "small_step": {
        "text": "احفظ الدعاء الوارد في الحديث.",
        "kind": "text_grounded",
        "grounded_in": ["hadith:bukhari:1"],
    },
}


@pytest.fixture
def media(tmp_path: Path) -> Path:
    return tmp_path / "media"


@pytest.fixture
def photos(media: Path, account_app, account_settings, guard) -> PhotoStore:
    """A store on the test's directory; the application reads real insights and allows texts."""
    store = PhotoStore(
        LocalStorage(
            media,
            base_url="https://api.tabsira.test",
            signing_key=b"k" * 32,
            default_ttl_seconds=300,
        ),
        account_settings,
    )
    account_app.state.photo_store = store
    account_app.state.insight_source = InsightTableSource()
    guard.verdict = ALLOW
    return store


@pytest.fixture
async def world(db_session: AsyncSession, scripture: None) -> None:
    await world_data.load_world(db_session)


def objects(media: Path) -> list[str]:
    return sorted(f"{path.parent.parent.name}/{path.name}" for path in media.rglob("*.jpg"))


async def consent(member: Member, *, granted: bool = True) -> None:
    response = await member.http.post(
        "/consents", json={"kind": "photo_storage", "version": "v1", "granted": granted}
    )
    assert response.status_code in (200, 201), response.text


async def kept_insight(
    db: AsyncSession, member: Member, photos: PhotoStore, *, with_photo: bool = True, **values: Any
) -> Insight:
    """A verified insight of `member` whose photo «تمّ» kept, the private object in the store."""
    owner = Owner(user_id=member.user.id)
    scan = scan_row(owner, status="done")
    db.add(scan)
    await db.flush()
    if with_photo:
        key = new_private_key()
        await photos.storage.put(key, jpeg_of(pixels()))
        values["photo_key"] = key
    insight = insight_row(owner, scan_id=scan.id, **{**EVIDENCE, **values})
    db.add(insight)
    await db.flush()
    return insight


async def keys_of(db: AsyncSession, insight: Insight) -> tuple[str | None, str | None]:
    """The two keys as the database holds them now; the row the test holds may be stale."""
    row = (
        await db.execute(
            select(Insight.photo_key, Insight.photo_public_key).where(Insight.id == insight.id)
        )
    ).one()
    return row[0], row[1]


async def post_with_photo(member: Member, insight: Insight, *, photo: bool = True) -> str:
    draft = await member.http.post("/posts", json={"insight_id": str(insight.id), "photo": photo})
    assert draft.status_code == 201, draft.text
    return str(draft.json()["id"])


async def place_with_photo(member: Member, insight: Insight, *, photo: bool = True) -> Any:
    response = await member.http.put(f"/insights/{insight.id}/map", json={**EXACT, "photo": photo})
    assert response.status_code == 200, response.text
    return response


def address_of(photos: PhotoStore, public_key: str) -> str:
    """The address a reader is given, and the only way the public copy is ever named."""
    url = photos.storage.public_url(public_key)
    assert url == f"https://api.tabsira.test/media/{public_key}"
    return url


def names_no_key(photos: PhotoStore, text: str, *, private: str, public: str) -> bool:
    """The private key is nowhere; the public one appears inside its address and nowhere else."""
    return private not in text and public not in text.replace(address_of(photos, public), "")


# ─── Posts ───


async def test_a_post_publishes_the_photo_the_owner_chose_and_withdrawing_removes_the_copy(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    private = insight.photo_key

    post_id = await post_with_photo(author, insight)
    drafted = await db_session.scalar(
        select(InsightPublication).order_by(InsightPublication.id.desc())
    )
    assert drafted.photo_ref == private
    # A draft shows nothing yet: no public copy.
    assert objects(media) == [private]

    submitted = await author.http.post(f"/posts/{post_id}/submit")
    assert submitted.json()["status"] == "published", submitted.text
    kept, public = await keys_of(db_session, insight)
    assert kept == private and public is not None and public.startswith("public/")
    assert objects(media) == sorted([private, public])
    assert submitted.json()["insight"]["has_photo"] is True
    read = await author.http.get(f"/posts/{post_id}")
    for text in (submitted.text, read.text):
        assert names_no_key(photos, text, private=private, public=public)
    # The address names the public copy alone, and the feeds give the same one.
    assert submitted.json()["insight"]["photo_url"] == address_of(photos, public)
    assert read.json()["insight"]["photo_url"] == address_of(photos, public)
    latest = await author.http.get("/feed/latest")
    assert [item["insight"]["photo_url"] for item in latest.json()["items"]] == [
        address_of(photos, public)
    ]
    mine = await author.http.get("/me/posts")
    assert mine.json()["items"][0]["insight"]["photo_url"] == address_of(photos, public)

    assert (await author.http.delete(f"/posts/{post_id}")).status_code == 204
    assert await keys_of(db_session, insight) == (private, None)
    # The owner's private copy stays; only the public one went.
    assert objects(media) == [private]


async def test_a_draft_names_no_address_and_the_owner_s_view_says_a_photo_is_kept(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    kept = await kept_insight(db_session, author, photos)
    bare = await kept_insight(db_session, author, photos, with_photo=False)

    post_id = await post_with_photo(author, kept)
    draft = await author.http.get(f"/posts/{post_id}")
    assert draft.json()["status"] == "draft"
    assert (
        draft.json()["insight"] | {"has_photo": True, "photo_url": None} == draft.json()["insight"]
    )
    own = await author.http.get(f"/insights/{kept.id}")
    assert own.status_code == 200, own.text
    assert own.json()["image"]["has_photo"] is True
    assert kept.photo_key not in own.text
    assert (await author.http.get(f"/insights/{bare.id}")).json()["image"]["has_photo"] is False


async def test_without_the_choice_or_a_kept_photo_a_post_shows_none(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    kept = await kept_insight(db_session, author, photos)
    bare = await kept_insight(db_session, author, photos, with_photo=False)

    not_chosen = await post_with_photo(author, kept, photo=False)
    nothing_kept = await post_with_photo(author, bare, photo=True)
    for post_id in (not_chosen, nothing_kept):
        response = await author.http.post(f"/posts/{post_id}/submit")
        assert response.json()["status"] == "published"
        assert response.json()["insight"]["has_photo"] is False
        assert response.json()["insight"]["photo_url"] is None

    assert objects(media) == [kept.photo_key]
    assert await keys_of(db_session, kept) == (kept.photo_key, None)


async def test_a_post_for_followers_only_makes_no_public_copy(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    draft = await author.http.post(
        "/posts", json={"insight_id": str(insight.id), "photo": True, "visibility": "followers"}
    )
    assert draft.status_code == 201, draft.text

    response = await author.http.post(f"/posts/{draft.json()['id']}/submit")

    # The owner's choice is recorded, but the `public/` prefix is for public posts alone.
    assert response.json()["status"] == "published"
    assert response.json()["insight"]["has_photo"] is True
    assert response.json()["insight"]["photo_url"] is None
    assert await keys_of(db_session, insight) == (insight.photo_key, None)
    assert objects(media) == [insight.photo_key]


async def test_a_followers_only_post_never_names_the_copy_a_map_entry_made(
    db_session, make_member, photos, media, world
):
    """The copy exists for the entry; a post for followers still gives nobody its address."""
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    await place_with_photo(author, insight)
    assert (await author.http.post(f"/insights/{insight.id}/map/publish")).status_code == 200
    _, public = await keys_of(db_session, insight)
    assert public is not None
    draft = await author.http.post(
        "/posts", json={"insight_id": str(insight.id), "photo": True, "visibility": "followers"}
    )

    response = await author.http.post(f"/posts/{draft.json()['id']}/submit")

    assert response.json()["status"] == "published"
    assert response.json()["insight"]["photo_url"] is None
    assert public not in response.text


async def test_the_rules_are_checked_again_when_the_copy_would_be_made(
    db_session, make_member, photos, media, world, caplog
):
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    post_id = await post_with_photo(author, insight)
    # The consent went between the draft and the publication.
    await consent(author, granted=False)

    with caplog.at_level(logging.WARNING, logger="tabsira.photos"):
        response = await author.http.post(f"/posts/{post_id}/submit")

    # The withdrawal already deleted the kept copy; the post is published without any photo.
    assert response.json()["status"] == "published"
    assert await keys_of(db_session, insight) == (None, None)
    assert objects(media) == []
    assert caplog.records == []


async def test_a_store_that_fails_does_not_stop_the_publication(
    db_session, make_member, photos, media, world, account_app, caplog, retry_requests
):
    class Failing(LocalStorage):
        async def copy(self, source: str, destination: str) -> None:
            raise StorageUnavailableError("down")

    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    post_id = await post_with_photo(author, insight)
    account_app.state.photo_store = PhotoStore(
        Failing(
            media,
            base_url="https://api.tabsira.test",
            signing_key=b"k" * 32,
            default_ttl_seconds=300,
        ),
        photos.settings,
    )

    with caplog.at_level(logging.WARNING, logger="tabsira.photos"):
        response = await author.http.post(f"/posts/{post_id}/submit")

    assert response.json()["status"] == "published"
    assert await keys_of(db_session, insight) == (insight.photo_key, None)
    assert [record.getMessage() for record in caplog.records] == [
        f"public copy of insight {insight.id} not updated: the photo store failed"
    ]
    # The worker is asked to reconcile once the store answers again.
    assert retry_requests.requests == 1


# ─── Map entries, and both at once ───


async def test_a_map_entry_shows_the_photo_while_published_and_shares_the_copy_with_a_post(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    private = insight.photo_key

    placed = await place_with_photo(author, insight)
    assert placed.json()["photo"] is True
    assert await keys_of(db_session, insight) == (private, None)
    published = await author.http.post(f"/insights/{insight.id}/map/publish")
    assert published.status_code == 200, published.text
    _, public = await keys_of(db_session, insight)
    assert public is not None and objects(media) == sorted([private, public])
    for text in (placed.text, published.text):
        assert private not in text and public not in text
    entry_id = published.json()["id"]
    public_page = await author.http.get(f"/atlas/entries/{entry_id}")
    assert public_page.status_code == 200
    assert names_no_key(photos, public_page.text, private=private, public=public)
    assert public_page.json()["photo_url"] == address_of(photos, public)
    # Anyone with the address reads the copy; the private copy has no public address at all.
    served = await author.http.get(urlsplit(address_of(photos, public)).path)
    assert (served.status_code, served.headers["content-type"]) == (200, "image/jpeg")
    assert served.headers["cache-control"] == "public, max-age=300"
    assert served.content == await photos.storage.get(public)
    assert (await author.http.get(f"/media/{private}")).status_code == 404

    # A post shows the same photo: one copy serves both, and it goes with the last of them.
    post_id = await post_with_photo(author, insight)
    assert (await author.http.post(f"/posts/{post_id}/submit")).json()["status"] == "published"
    assert await keys_of(db_session, insight) == (private, public)
    assert (await author.http.delete(f"/insights/{insight.id}/map")).status_code == 204
    assert await keys_of(db_session, insight) == (private, public)
    assert (await author.http.delete(f"/posts/{post_id}")).status_code == 204
    assert await keys_of(db_session, insight) == (private, None)
    assert objects(media) == [private]


async def test_a_map_entry_placed_without_the_choice_makes_no_copy(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)

    placed = await place_with_photo(author, insight, photo=False)
    assert placed.json()["photo"] is False
    published = await author.http.post(f"/insights/{insight.id}/map/publish")
    assert published.status_code == 200
    page = await author.http.get(f"/atlas/entries/{published.json()['id']}")
    assert page.json()["photo_url"] is None
    assert (await author.http.delete(f"/insights/{insight.id}/map")).status_code == 204

    assert await keys_of(db_session, insight) == (insight.photo_key, None)
    assert objects(media) == [insight.photo_key]


@pytest.mark.parametrize("photo_again", [True, False])
async def test_re_placing_a_published_entry_takes_the_copy_down_with_the_draft(
    db_session, make_member, photos, media, world, photo_again
):
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    await place_with_photo(author, insight)
    assert (await author.http.post(f"/insights/{insight.id}/map/publish")).status_code == 200
    _, public = await keys_of(db_session, insight)
    assert public is not None

    # The entry is a draft again: nothing shows the photo, whatever the new choice says.
    placed = await place_with_photo(author, insight, photo=photo_again)

    assert placed.json()["status"] == "draft" and placed.json()["photo"] is photo_again
    assert await keys_of(db_session, insight) == (insight.photo_key, None)
    assert objects(media) == [insight.photo_key]
    # Publishing the new draft makes the copy again only when the photo is still chosen.
    assert (await author.http.post(f"/insights/{insight.id}/map/publish")).status_code == 200
    _, again = await keys_of(db_session, insight)
    assert (again is not None) is photo_again


async def test_a_withdrawn_consent_deletes_both_copies_at_once_whatever_still_shows_them(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    post_id = await post_with_photo(author, insight)
    assert (await author.http.post(f"/posts/{post_id}/submit")).json()["status"] == "published"
    await place_with_photo(author, insight)
    assert (await author.http.post(f"/insights/{insight.id}/map/publish")).status_code == 200
    _private, public = await keys_of(db_session, insight)
    assert public is not None

    await consent(author, granted=False)

    assert await keys_of(db_session, insight) == (None, None)
    assert objects(media) == []
    with pytest.raises(ObjectNotFoundError):
        await photos.storage.get(public)
    # The publications stay up without a photo; taking them down asks nothing of the store.
    assert (await author.http.delete(f"/insights/{insight.id}/map")).status_code == 204
    assert (await author.http.delete(f"/posts/{post_id}")).status_code == 204
    assert objects(media) == []


# ─── A moderator's decisions ───


async def test_a_moderator_s_removal_deletes_the_copy_and_a_restoration_makes_it_again(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    post_id = await post_with_photo(author, insight)
    assert (await author.http.post(f"/posts/{post_id}/submit")).json()["status"] == "published"
    post = await db_session.get(Post, int(post_id))
    _, first_public = await keys_of(db_session, insight)
    assert first_public is not None

    await moderation_service.remove(db_session, post, MODERATOR_ID, "spam", photos=photos)
    assert await keys_of(db_session, insight) == (insight.photo_key, None)
    await moderation_service.approve(db_session, post, MODERATOR_ID, photos=photos)
    _, again = await keys_of(db_session, insight)
    assert again is not None and again != first_public
    assert objects(media) == sorted([insight.photo_key, again])

    # Without a store the decision stands and the copy is left as it is; a comment has no photo.
    await moderation_service.remove(db_session, post, MODERATOR_ID, "spam")
    assert await keys_of(db_session, insight) == (insight.photo_key, again)
    comment = await new_comment(db_session, await new_post(db_session, author.user), author.user)
    await moderation_service.remove(db_session, comment, MODERATOR_ID, "spam", photos=photos)
    assert await keys_of(db_session, insight) == (insight.photo_key, again)

    # A publication whose insight is gone, or whose insight kept no photo, asks nothing of the store.
    gone = InsightPublication(
        author_id=author.user.id,
        insight_id=any_id(),
        insight_version=1,
        title="t",
        glimpse="g",
        relation_type="direct",
        quran_refs=[{"surah": 112, "ayah": 1}],
        hadith_refs=[],
        explanation_excerpt="e",
        photo_ref="private/" + "c" * 32 + ".jpg",
    )
    db_session.add(gone)
    await db_session.flush()
    orphan = Post(
        author_id=author.user.id,
        publication_id=gone.id,
        status=PostStatus.PUBLISHED,
        published_at=clock.utcnow(),
    )
    db_session.add(orphan)
    await db_session.flush()
    await moderation_service.remove(db_session, orphan, MODERATOR_ID, "spam", photos=photos)
    plain = await new_post(db_session, author.user, status=PostStatus.PUBLISHED)
    await moderation_service.remove(db_session, plain, MODERATOR_ID, "spam", photos=photos)
    bare = await kept_insight(db_session, author, photos, with_photo=False)
    await place_with_photo(author, bare)
    published = await author.http.post(f"/insights/{bare.id}/map/publish")
    entry = await db_session.get(MapEntry, int(published.json()["id"]))
    await moderation_service.remove(db_session, entry, MODERATOR_ID, "wrong_place", photos=photos)
    assert objects(media) == sorted([insight.photo_key, again])


async def test_a_moderator_s_removal_of_a_map_entry_deletes_the_copy(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    insight = await kept_insight(db_session, author, photos)
    await place_with_photo(author, insight)
    published = await author.http.post(f"/insights/{insight.id}/map/publish")
    entry = await db_session.get(MapEntry, int(published.json()["id"]))
    assert (await keys_of(db_session, insight))[1] is not None

    await moderation_service.remove(db_session, entry, MODERATOR_ID, "wrong_place", photos=photos)

    assert await keys_of(db_session, insight) == (insight.photo_key, None)
    assert objects(media) == [insight.photo_key]


# ─── The local media route ───


async def test_the_media_route_serves_the_public_prefix_alone_and_only_from_the_local_disk(
    db_session, make_member, photos, media, world, account_app
):
    reader = await make_member(signed_in=False)
    public = new_public_key()
    await photos.storage.put(public, jpeg_of(pixels()))

    assert (await reader.http.get(f"/media/{public}")).status_code == 200
    # A name that is not a key never reaches the disk; an absent copy is simply not found.
    assert (await reader.http.get("/media/public/../../etc/passwd")).status_code in (404, 422)
    assert (await reader.http.get("/media/public/not-a-key.jpg")).status_code == 422
    assert (await reader.http.get(f"/media/{new_public_key()}")).status_code == 404
    assert (await reader.http.get(f"/media/{new_private_key()}")).status_code == 404

    # With S3 the copies are read from `S3_PUBLIC_BASE_URL`, never through the API.
    account_app.state.photo_store = PhotoStore(cast("Storage", object()), photos.settings)
    assert (await reader.http.get(f"/media/{public}")).status_code == 404


async def report(member: Member, target_type: str, target_id: Any) -> None:
    response = await member.http.post(
        "/reports",
        json={"target_type": target_type, "target_id": str(target_id), "reason": "abuse"},
    )
    assert response.status_code == 201, response.text


async def test_reports_that_hold_a_post_and_an_entry_take_their_copies_down_until_approved(
    db_session, make_member, photos, media, world, account_app, account_settings
):
    account_app.state.settings = account_settings.model_copy(
        update={"social_report_hold_threshold": 1}
    )
    author = await make_member("author")
    reporter = await make_member("reporter")
    await consent(author)
    posted = await kept_insight(db_session, author, photos)
    post_id = await post_with_photo(author, posted)
    assert (await author.http.post(f"/posts/{post_id}/submit")).json()["status"] == "published"
    placed = await kept_insight(db_session, author, photos)
    await place_with_photo(author, placed)
    published = await author.http.post(f"/insights/{placed.id}/map/publish")
    assert (await keys_of(db_session, posted))[1] is not None
    assert (await keys_of(db_session, placed))[1] is not None

    await report(reporter, "post", post_id)
    await report(reporter, "map_entry", published.json()["id"])

    post = await db_session.get(Post, int(post_id))
    entry = await db_session.get(MapEntry, int(published.json()["id"]))
    assert post.status is PostStatus.PENDING_REVIEW and entry.status.value == "pending_review"
    assert await keys_of(db_session, posted) == (posted.photo_key, None)
    assert await keys_of(db_session, placed) == (placed.photo_key, None)
    assert objects(media) == sorted([posted.photo_key, placed.photo_key])

    # Approved: the copies come back. Refused after a hold: they go for good.
    await moderation_service.approve(db_session, post, MODERATOR_ID, photos=photos)
    await moderation_service.approve(db_session, entry, MODERATOR_ID, photos=photos)
    assert (await keys_of(db_session, posted))[1] is not None
    assert (await keys_of(db_session, placed))[1] is not None
    # A hold without a store leaves the copy, as every path does; the refusal deletes it.
    another = await make_member("another")
    for target_type, item in ((ReportTarget.POST, post), (ReportTarget.MAP_ENTRY, entry)):
        db_session.add(
            Report(
                reporter_id=another.user.id,
                target_type=target_type,
                target_id=item.id,
                reason=ReportReason.ABUSE,
            )
        )
    await db_session.flush()
    assert await moderation_service.hold_if_reported(db_session, post, 1) is True
    assert await moderation_service.hold_if_reported(db_session, entry, 1) is True
    assert (await keys_of(db_session, posted))[1] is not None
    assert (await keys_of(db_session, placed))[1] is not None
    await moderation_service.reject(db_session, post, MODERATOR_ID, "spam", photos=photos)
    await moderation_service.reject(db_session, entry, MODERATOR_ID, "wrong_place", photos=photos)
    assert post.status is PostStatus.REJECTED and entry.status.value == "removed"
    assert await keys_of(db_session, posted) == (posted.photo_key, None)
    assert await keys_of(db_session, placed) == (placed.photo_key, None)
    assert objects(media) == sorted([posted.photo_key, placed.photo_key])


# ─── A store that failed a deletion: the reconcile ───


def failing_store(media: Path, settings: Any) -> PhotoStore:
    class Down(LocalStorage):
        async def delete(self, key: str) -> None:
            raise StorageUnavailableError("down")

    return PhotoStore(
        Down(
            media,
            base_url="https://api.tabsira.test",
            signing_key=b"k" * 32,
            default_ttl_seconds=300,
        ),
        settings,
    )


async def test_a_copy_the_store_failed_to_delete_goes_with_the_reconcile(
    db_session, make_member, photos, media, world, account_app, caplog, retry_requests, engine
):
    author = await make_member("author")
    await consent(author)
    withdrawn = await kept_insight(db_session, author, photos)
    still_shown = await kept_insight(db_session, author, photos)
    posts = []
    for insight in (withdrawn, still_shown):
        posts.append(await post_with_photo(author, insight))
        assert (await author.http.post(f"/posts/{posts[-1]}/submit")).json()[
            "status"
        ] == "published"
    _, orphan = await keys_of(db_session, withdrawn)
    _, live = await keys_of(db_session, still_shown)
    account_app.state.photo_store = failing_store(media, photos.settings)

    with caplog.at_level(logging.WARNING, logger="tabsira.photos"):
        response = await author.http.delete(f"/posts/{posts[0]}")
    # The withdrawal of the first post: the person is answered, the copy stays, a retry is asked.
    assert response.status_code == 204
    assert await keys_of(db_session, withdrawn) == (withdrawn.photo_key, orphan)
    assert retry_requests.requests == 1
    assert caplog.records[0].getMessage() == (
        f"public copy of insight {withdrawn.id} not updated: the photo store failed"
    )

    # Another run holds the lock: this one steps aside and touches nothing.
    async with engine.connect() as other, other.begin():
        await other.execute(
            sql("SELECT pg_advisory_xact_lock(:key)"), {"key": photo_service.RECONCILE_LOCK_KEY}
        )
        aside = await photo_service.reconcile_public_copies(db_session, photos)
    assert (aside.checked, aside.skipped) == (0, True)

    # The store still down: the reconcile counts the failure and asks for no second retry.
    failed = await photo_service.reconcile_public_copies(db_session, account_app.state.photo_store)
    assert (failed.checked, failed.deleted, failed.failed, failed.skipped) == (2, 0, 1, False)
    assert retry_requests.requests == 1

    # The store is back: the orphan goes, the copy a live post shows stays.
    report = await photo_service.reconcile_public_copies(db_session, photos)
    assert (report.checked, report.deleted, report.failed, report.skipped) == (2, 1, 0, False)
    assert await keys_of(db_session, withdrawn) == (withdrawn.photo_key, None)
    assert await keys_of(db_session, still_shown) == (still_shown.photo_key, live)
    assert objects(media) == sorted([withdrawn.photo_key, still_shown.photo_key, live])


# ─── The account export ───


async def test_the_export_states_the_photo_of_a_post_as_facts_and_never_as_a_key(
    db_session, make_member, photos, media, world
):
    author = await make_member("author")
    await consent(author)
    shown = await kept_insight(db_session, author, photos)
    chosen_no_copy = await kept_insight(db_session, author, photos)
    shown_post = await post_with_photo(author, shown)
    assert (await author.http.post(f"/posts/{shown_post}/submit")).json()["status"] == "published"
    # Chosen for a post to followers only: no public copy is ever made (and none exists).
    followers = await author.http.post(
        "/posts",
        json={"insight_id": str(chosen_no_copy.id), "photo": True, "visibility": "followers"},
    )
    followers_post = str(followers.json()["id"])
    assert (await author.http.post(f"/posts/{followers_post}/submit")).status_code == 200
    bare_post = await post_with_photo(author, chosen_no_copy, photo=False)
    # A withdrawn post keeps no publication at all.
    withdrawn_post = await post_with_photo(author, shown)
    assert (await author.http.post(f"/posts/{withdrawn_post}/submit")).status_code == 200
    assert (await author.http.delete(f"/posts/{withdrawn_post}")).status_code == 204
    _, public = await keys_of(db_session, shown)
    assert public is not None

    response = await author.http.get("/account/export")

    assert response.status_code == 200
    facts = {
        post["id"]: (
            None
            if post["publication"] is None
            else (post["publication"]["has_photo"], post["publication"]["published"])
        )
        for post in response.json()["social"]["posts"]
    }
    assert facts == {
        shown_post: (True, True),
        followers_post: (True, False),
        bare_post: (False, False),
        withdrawn_post: None,
    }
    assert "photo_ref" not in response.text
    for key in (shown.photo_key, chosen_no_copy.photo_key, public):
        assert key not in response.text
    assert response.json()["learning"]["photos"] == [
        {"insight_id": str(shown.id), "published": True},
        {"insight_id": str(chosen_no_copy.id), "published": False},
    ]
