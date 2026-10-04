"""Posts: the draft made from a verified insight, the guard, the audience, withdrawal."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text

from src.models import (
    Bookmark,
    Comment,
    CommentStatus,
    InsightPublication,
    ModerationAction,
    Post,
    PostLike,
    PostStatus,
    PostVisibility,
)
from src.scripture.text import sha256_hex
from src.services.insight_source import HadithRef, QuranRef
from src.services.post_view import outcome_message
from src.services.social_limits import SocialLimits, WriteKind
from tests.helpers import any_id
from tests.scripture.fixtures import hadith_text, verse_text
from tests.support_social import (
    ALLOW,
    REJECT,
    REVIEW,
    draft_post,
    publish_post,
    snapshot_for,
)

MODERATOR = uuid.uuid4()

# ─── Making a draft ───────────────────────────────────────────────────────────


create = draft_post


async def test_a_draft_is_made_from_a_verified_insight_and_cites_the_store_by_reference(
    make_member, make_insight, db_session
):
    author = await make_member("author")
    insight = make_insight(author)

    response = await create(author, insight, reflection="  تأمّلي الشخصي  ")

    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "draft"
    assert body["visibility"] == "public"
    assert body["author"] == {"handle": "author", "public_name": "author name"}
    assert body["published_at"] is None
    assert body["reflection"] == {
        "text": "تأمّلي الشخصي",
        "source": "user",
        "verified": False,
        "looks_like_scripture": False,
    }
    shown = body["insight"]
    assert (shown["title"], shown["glimpse"], shown["insight_version"]) == (
        "ماء يجري",
        "الماء يعلّمنا الجريان",
        3,
    )
    assert (shown["explanation"], shown["step"], shown["concepts"]) == (
        "شرح موجز من التطبيق",
        "اشرب ماءً بهدوء",
        ["water"],
    )
    publication = await db_session.scalar(select(InsightPublication))
    assert publication.quran_refs == [{"surah": 112, "ayah": 1}]
    assert publication.hadith_refs == [{"collection": "bukhari", "number": "1"}]
    assert publication.insight_id == insight.insight_id


async def test_the_scripture_in_a_response_is_the_stored_text_with_its_stored_hash(
    make_member, make_insight, db_session
):
    author = await make_member("author")

    body = (await create(author, make_insight(author))).json()

    verse = body["insight"]["quran"][0]
    hadith = body["insight"]["hadith"][0]
    assert verse["text"] == verse_text(112, 1)
    assert verse["sha256"] == sha256_hex(verse["text"])
    assert (verse["surah"], verse["ayah"], verse["verified"]) == (112, 1, True)
    assert verse["surah_name"] == "سورة الإخلاص"
    assert verse["source_url"].startswith("https://quranpedia.net/surah/2/112#verse-")
    assert hadith["text"] == hadith_text("bukhari", 1)
    assert hadith["sha256"] == sha256_hex(hadith["text"])
    assert (hadith["collection"], hadith["number"], hadith["classification"]) == (
        "bukhari",
        "1",
        "صحيح",
    )
    assert hadith["verification_url"].startswith("https://dorar.net/hadith/search?")
    # The publication row holds references and no scripture at all.
    row = await db_session.scalar(select(InsightPublication))
    assert verse_text(112, 1) not in repr(
        [row.title, row.glimpse, row.explanation_excerpt, row.quran_refs]
    )
    assert {c.name for c in InsightPublication.__table__.columns}.isdisjoint(
        {"text", "verse", "hadith"}
    )


async def test_a_reflection_that_reads_like_scripture_stays_the_users_text_and_is_flagged(
    make_member, make_insight
):
    author = await make_member("author")
    quoted = "قال تعالى: «قل هو الله أحد الله الصمد لم يلد»"

    body = (await create(author, make_insight(author), reflection=quoted)).json()

    assert body["reflection"]["text"] == quoted
    assert body["reflection"]["looks_like_scripture"] is True
    assert body["reflection"]["verified"] is False
    assert body["reflection"]["source"] == "user"
    # The badge belongs to the evidence, never to the reflection.
    assert body["insight"]["quran"][0]["verified"] is True


async def test_a_draft_without_a_reflection_has_none(make_member, make_insight):
    author = await make_member("author")

    body = (await create(author, make_insight(author), reflection="   ")).json()

    assert body["reflection"] is None


async def test_a_draft_needs_a_session_a_verified_address_and_a_public_identity(
    make_member, make_insight
):
    guest = await make_member(signed_in=False)
    unverified = await make_member("fresh", verified=False)
    nameless = await make_member("nameless", identity=False)
    insight = make_insight(nameless)

    assert (await create(guest, insight)).status_code == 401
    assert (await create(unverified, make_insight(unverified))).json()[
        "error"
    ] == "EMAIL_NOT_VERIFIED"
    refused = await create(nameless, insight)
    assert (refused.status_code, refused.json()["error"]) == (409, "PUBLIC_IDENTITY_REQUIRED")


async def test_an_insight_that_is_not_the_callers_or_does_not_exist_is_a_404(
    make_member, make_insight
):
    author = await make_member("author")
    other = await make_member("other")
    theirs = make_insight(other)

    stranger = await create(author, theirs)
    nothing = await author.http.post("/posts", json={"insight_id": str(any_id())})

    # Someone else's insight answers exactly as one that does not exist.
    assert stranger.status_code == nothing.status_code == 404
    assert stranger.json() == nothing.json()


async def test_publishing_without_an_insight_source_answers_503(account_app, make_member):
    author = await make_member("author")
    account_app.state.insight_source = None

    response = await author.http.post("/posts", json={"insight_id": str(any_id())})

    assert (response.status_code, response.json()["error"]) == (503, "SERVICE_UNAVAILABLE")


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"verified": False}, "not verified"),
        ({"quran_refs": (), "hadith_refs": ()}, "cites no evidence"),
        ({"title": "ت" * 201}, "longer than 200"),
        ({"relation_type": "r" * 33}, "longer than 32"),
        ({"title": "   "}, "no title"),
        ({"glimpse": ""}, "no title or no glimpse"),
        ({"quran_refs": (QuranRef(112, 1),) * 4}, "more than 3"),
        (
            {"quran_refs": (QuranRef(112, 1), QuranRef(114, 99))},
            "verse it cites is not in the store",
        ),
        ({"hadith_refs": (HadithRef("bukhari", "9999"),)}, "missing or has no sahih"),
        ({"hadith_refs": (HadithRef("bukhari", "8"),)}, "missing or has no sahih"),
        ({"hadith_refs": (HadithRef("muslim", "1"),)}, "missing or has no sahih"),
        ({"glimpse": "قال تعالى: «قل هو الله أحد الله الصمد»"}, "looks like scripture"),
        ({"explanation_excerpt": "﴿قُلْ هُوَ ٱللَّهُ أَحَدٌ﴾"}, "looks like scripture"),  # noqa: RUF001 - the ornate brackets are the point
    ],
)
async def test_an_insight_that_cannot_be_published_is_refused_with_its_reason(
    make_member, make_insight, db_session, overrides, why
):
    author = await make_member("author")

    response = await create(author, make_insight(author, **overrides))

    assert response.status_code == 409
    assert response.json()["error"] == "INSIGHT_NOT_PUBLISHABLE"
    assert why in response.json()["detail"]
    assert await db_session.scalar(select(func.count()).select_from(Post)) == 0
    assert await db_session.scalar(select(func.count()).select_from(InsightPublication)) == 0


async def test_an_insight_whose_snapshot_names_another_owner_or_id_is_not_trusted(
    make_member, account_app, scripture
):
    author = await make_member("author")
    other = await make_member("other")
    asked = any_id()
    foreign = snapshot_for(other, insight_id=asked)
    renamed = snapshot_for(author, insight_id=any_id())

    class Careless:
        """A source that answers with someone else's insight, or with another one."""

        def __init__(self, answer):
            self.answer = answer

        async def load_for_publishing(self, db, insight_id, owner_id):
            return self.answer

    for answer in (foreign, renamed):
        account_app.state.insight_source = Careless(answer)

        response = await author.http.post("/posts", json={"insight_id": str(asked)})

        assert response.status_code == 404


async def test_a_photo_is_kept_only_when_its_owner_agreed_and_the_scene_is_not_sensitive(
    make_member, make_insight, db_session
):
    author = await make_member("author")
    cases = {
        "agreed": ({"photo_ref": "photos/a", "photo_consent": True}, "photos/a"),
        "no consent": ({"photo_ref": "photos/b", "photo_consent": False}, None),
        "sensitive": (
            {"photo_ref": "photos/c", "photo_consent": True, "scene_sensitive": True},
            None,
        ),
        "no photo": ({"photo_consent": True}, None),
        "too long": ({"photo_ref": "p" * 513, "photo_consent": True}, None),
    }

    for name, (overrides, expected) in cases.items():
        body = (await create(author, make_insight(author, **overrides))).json()
        assert body["insight"]["photo_ref"] == expected, name


async def test_concepts_are_trimmed_and_capped(make_member, make_insight):
    author = await make_member("author")
    concepts = ("a", " b ", "", "  ", "c", "d", "e", "f", "g")

    body = (await create(author, make_insight(author, concepts=concepts))).json()

    assert body["insight"]["concepts"] == ["a", "b", "c", "d", "e"]


async def test_a_reflection_over_the_limit_or_with_control_characters_is_refused(
    make_member, make_insight
):
    author = await make_member("author")
    insight = make_insight(author)

    long = await create(author, insight, reflection="ا" * 801)  # noqa: RUF001
    control = await create(author, insight, reflection="a\u0007b")
    paragraphs = await create(author, insight, reflection="سطر\nسطر\tثان")  # noqa: RUF001

    assert (long.status_code, control.status_code, paragraphs.status_code) == (422, 422, 201)


async def test_text_that_can_reverse_how_a_line_reads_is_refused_but_the_arabic_marks_stay(
    make_member, make_insight
):
    author = await make_member("author")
    insight = make_insight(author)

    override = await create(author, insight, reflection="safe \u202etxet")
    isolate = await create(author, insight, reflection="a \u2066b")
    marks = await create(author, insight, reflection="\u200fنص\u200f")

    assert (override.status_code, isolate.status_code, marks.status_code) == (422, 422, 201)


async def test_a_moderators_own_words_are_never_returned_as_the_reason(
    make_member, make_insight, guard, db_session
):
    from src.services import moderation_service

    author = await make_member("author")
    post_id = await published(author, make_insight)
    post = await db_session.get(Post, int(post_id))
    await moderation_service.remove(db_session, post, MODERATOR, "free words of a moderator")
    await db_session.flush()

    item = (await author.http.get("/me/posts")).json()["items"][0]

    assert item["status"] == "removed"
    assert item["status_reason"] is None
    assert item["status_message"] == "لم يُقبل لأنه يخالف قواعد المجتمع."
    assert "free words" not in str(item)


async def test_unknown_fields_are_refused(make_member, make_insight):
    author = await make_member("author")

    response = await create(author, make_insight(author), status="published")

    assert response.status_code == 422


async def test_posts_are_rate_limited_per_account(make_member, make_insight, account_app):
    account_app.state.social_limits = SocialLimits({WriteKind.POST: (1, 100, 60)})
    author = await make_member("author")
    insight = make_insight(author)

    first = await create(author, insight)
    second = await create(author, insight)

    assert (first.status_code, second.status_code) == (201, 429)
    assert second.json()["error"] == "RATE_LIMITED"


# ─── Who can see a draft ──────────────────────────────────────────────────────


async def test_a_draft_is_visible_to_its_author_alone(make_member, make_insight):
    author = await make_member("author")
    other = await make_member("other")
    guest = await make_member(signed_in=False)
    post_id = (await create(author, make_insight(author))).json()["id"]

    assert (await author.http.get(f"/posts/{post_id}")).status_code == 200
    assert (await other.http.get(f"/posts/{post_id}")).status_code == 404
    assert (await guest.http.get(f"/posts/{post_id}")).status_code == 404
    assert (await guest.http.get(f"/posts/{any_id()}")).status_code == 404


# ─── Editing a draft ──────────────────────────────────────────────────────────


async def test_a_draft_can_be_edited_its_reflection_cleared_and_its_audience_changed(
    make_member, make_insight
):
    author = await make_member("author")
    post_id = (await create(author, make_insight(author), reflection="أولى")).json()["id"]

    edited = await author.http.patch(f"/posts/{post_id}", json={"reflection": "ثانية"})
    audience = await author.http.patch(f"/posts/{post_id}", json={"visibility": "followers"})
    cleared = await author.http.patch(f"/posts/{post_id}", json={"reflection": None})

    assert edited.json()["reflection"]["text"] == "ثانية"
    assert audience.json()["visibility"] == "followers"
    assert audience.json()["reflection"]["text"] == "ثانية"
    assert cleared.json()["reflection"] is None
    assert cleared.json()["visibility"] == "followers"


async def test_only_the_author_edits_a_draft_and_a_published_post_is_not_editable(
    make_member, make_insight, guard
):
    author = await make_member("author")
    other = await make_member("other")
    post_id = (await create(author, make_insight(author))).json()["id"]

    assert (
        await other.http.patch(f"/posts/{post_id}", json={"reflection": "x"})
    ).status_code == 404
    await author.http.post(f"/posts/{post_id}/submit")
    again = await author.http.patch(f"/posts/{post_id}", json={"reflection": "x"})

    assert (again.status_code, again.json()["error"]) == (409, "CONFLICT")


# ─── Submitting through the guard ─────────────────────────────────────────────


async def test_a_clear_post_is_published_at_once_and_the_guard_saw_only_the_reflection(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    post_id = (await create(author, make_insight(author), reflection="تأمل هادئ")).json()["id"]

    response = await author.http.post(f"/posts/{post_id}/submit")

    body = response.json()
    assert response.status_code == 200
    assert (body["status"], body["status_reason"], body["status_message"]) == (
        "published",
        None,
        None,
    )
    assert body["published_at"] is not None
    assert guard.texts == ["تأمل هادئ"]
    action = await db_session.scalar(select(ModerationAction))
    assert (action.action.value, action.source.value, action.reason) == (
        "published",
        "guard",
        "clear",
    )


async def test_a_post_with_no_words_of_the_author_is_published_without_asking_the_guard(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    post_id = (await create(author, make_insight(author))).json()["id"]

    body = (await author.http.post(f"/posts/{post_id}/submit")).json()

    assert body["status"] == "published"
    assert guard.texts == []
    assert (await db_session.scalar(select(ModerationAction))).reason == "no_user_text"


async def test_an_uncertain_post_waits_for_a_moderator_and_its_author_is_told(
    make_member, make_insight, guard, db_session
):
    guard.verdict = REVIEW
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    post_id = (await create(author, make_insight(author), reflection="x")).json()["id"]

    body = (await author.http.post(f"/posts/{post_id}/submit")).json()

    assert body["status"] == "pending_review"
    assert body["status_reason"] == "guard_uncertain"
    assert body["status_message"] == "يحتاج إلى مراجعة مشرف قبل نشره."
    assert (await guest.http.get(f"/posts/{post_id}")).status_code == 404
    assert (await author.http.get(f"/posts/{post_id}")).json()["status"] == "pending_review"
    assert (await db_session.scalar(select(ModerationAction))).action.value == "held"


async def test_a_guard_that_could_not_judge_holds_the_post_and_says_so(
    make_member, make_insight, guard
):
    from src.services.moderation_guard import GuardVerdict, Outcome

    guard.verdict = GuardVerdict(Outcome.REVIEW, "guard_unavailable", {"error": "timeout"})
    author = await make_member("author")
    post_id = (await create(author, make_insight(author), reflection="x")).json()["id"]

    body = (await author.http.post(f"/posts/{post_id}/submit")).json()

    assert body["status"] == "pending_review"
    assert body["status_message"] == "تعذّرت المراجعة الآلية الآن، فسيراجعه مشرف قبل نشره."


async def test_a_refused_post_tells_its_author_the_rule_and_can_be_edited_and_resubmitted(
    make_member, make_insight, guard
):
    guard.verdict = REJECT
    author = await make_member("author")
    post_id = (await create(author, make_insight(author), reflection="سيئ")).json()["id"]

    refused = (await author.http.post(f"/posts/{post_id}/submit")).json()
    guard.verdict = ALLOW
    edited = await author.http.patch(f"/posts/{post_id}", json={"reflection": "أحسن"})
    resubmitted = (await author.http.post(f"/posts/{post_id}/submit")).json()

    assert refused["status"] == "rejected"
    assert refused["status_message"] == "لم يُقبل لأنه يخالف قواعد المجتمع: إساءة أو مضايقة."
    assert (edited.json()["status"], edited.json()["status_reason"]) == ("draft", None)
    assert resubmitted["status"] == "published"


async def test_only_a_draft_can_be_submitted_and_only_by_its_author(
    make_member, make_insight, guard
):
    author = await make_member("author")
    other = await make_member("other")
    post_id = (await create(author, make_insight(author))).json()["id"]

    assert (await other.http.post(f"/posts/{post_id}/submit")).status_code == 404
    assert (await author.http.post(f"/posts/{post_id}/submit")).status_code == 200
    again = await author.http.post(f"/posts/{post_id}/submit")

    assert (again.status_code, again.json()["error"]) == (409, "CONFLICT")


async def test_a_post_edited_while_the_guard_judged_it_is_not_settled_on_the_old_words(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    post_id = (await create(author, make_insight(author), reflection="قبل")).json()["id"]

    async def edit_meanwhile():
        await db_session.execute(text("UPDATE app.posts SET reflection = 'بعد'"))
        db_session.expire_all()

    guard.during = edit_meanwhile

    response = await author.http.post(f"/posts/{post_id}/submit")

    assert (response.status_code, response.json()["error"]) == (409, "CONFLICT")
    assert (await db_session.scalar(select(Post))).status is PostStatus.DRAFT


# ─── Reading a published post ─────────────────────────────────────────────────


published = publish_post


async def test_a_published_post_is_public_to_a_guest_without_the_authors_private_details(
    make_member, make_insight, guard
):
    author = await make_member("author", display_name="Secret Real Name")
    guest = await make_member(signed_in=False)
    post_id = await published(author, make_insight, reflection="تأمل")

    response = await guest.http.get(f"/posts/{post_id}")

    body = response.json()
    assert response.status_code == 200
    assert body["viewer"] is None
    assert (body["like_count"], body["comment_count"]) == (0, 0)
    assert (body["status_reason"], body["status_message"], body["why"]) == (None, None, None)
    assert body["status"] == "published"
    for private in ("Secret Real Name", "author@example.com", str(author.user.id)):
        assert private not in response.text


async def test_a_followers_only_post_is_for_its_author_and_followers_and_otherwise_a_404(
    make_member, make_insight, guard
):
    author = await make_member("author")
    follower = await make_member("follower")
    stranger = await make_member("stranger")
    guest = await make_member(signed_in=False)
    post_id = await published(author, make_insight, visibility="followers")
    await follower.http.put("/u/author/follow")

    assert (await author.http.get(f"/posts/{post_id}")).status_code == 200
    assert (await follower.http.get(f"/posts/{post_id}")).status_code == 200
    assert (await stranger.http.get(f"/posts/{post_id}")).status_code == 404
    assert (await guest.http.get(f"/posts/{post_id}")).status_code == 404


async def test_a_post_is_a_404_behind_a_block_in_either_direction(make_member, make_insight, guard):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await published(author, make_insight)

    await reader.http.put("/blocks/author")
    assert (await reader.http.get(f"/posts/{post_id}")).status_code == 404
    await reader.http.delete("/blocks/author")
    await author.http.put("/blocks/reader")
    assert (await reader.http.get(f"/posts/{post_id}")).status_code == 404
    assert (await author.http.get(f"/posts/{post_id}")).status_code == 200


async def test_the_post_of_a_disabled_account_is_a_404(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    post_id = await published(author, make_insight)

    author.user.is_active = False
    await db_session.flush()

    assert (await guest.http.get(f"/posts/{post_id}")).status_code == 404


async def test_the_counts_and_the_viewers_own_flags_are_read_from_the_rows(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await published(author, make_insight)
    db_session.add_all(
        [
            PostLike(post_id=int(post_id), user_id=reader.user.id),
            PostLike(post_id=int(post_id), user_id=author.user.id),
            Bookmark(user_id=reader.user.id, post_id=int(post_id)),
            Comment(
                post_id=int(post_id),
                author_id=reader.user.id,
                body="a",
                status=CommentStatus.PUBLISHED,
            ),
            Comment(
                post_id=int(post_id),
                author_id=reader.user.id,
                body="b",
                status=CommentStatus.REJECTED,
            ),
        ]
    )
    await db_session.flush()

    seen_by_reader = (await reader.http.get(f"/posts/{post_id}")).json()
    seen_by_author = (await author.http.get(f"/posts/{post_id}")).json()

    assert (seen_by_reader["like_count"], seen_by_reader["comment_count"]) == (2, 1)
    assert seen_by_reader["viewer"] == {"liked": True, "bookmarked": True, "is_author": False}
    assert seen_by_author["viewer"] == {"liked": True, "bookmarked": False, "is_author": True}


# ─── Withdrawing ──────────────────────────────────────────────────────────────


async def test_a_withdrawn_post_is_gone_everywhere_and_its_content_is_erased(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    post_id = await published(author, make_insight, reflection="تأمل")
    pid = int(post_id)
    db_session.add_all(
        [
            PostLike(post_id=pid, user_id=reader.user.id),
            Bookmark(user_id=reader.user.id, post_id=pid),
            Comment(
                post_id=pid, author_id=reader.user.id, body="c", status=CommentStatus.PUBLISHED
            ),
        ]
    )
    await db_session.flush()

    response = await author.http.delete(f"/posts/{post_id}")

    assert response.status_code == 204
    for who in (author, reader, guest):
        gone = await who.http.get(f"/posts/{post_id}")
        assert (gone.status_code, gone.json()["error"]) == (410, "GONE")
    assert (await author.http.delete(f"/posts/{post_id}")).status_code == 410
    assert (
        await author.http.patch(f"/posts/{post_id}", json={"reflection": "x"})
    ).status_code == 410
    assert (await author.http.post(f"/posts/{post_id}/submit")).status_code == 410
    post = await db_session.scalar(select(Post))
    assert (post.status, post.reflection, post.publication_id) == (PostStatus.REMOVED, None, None)
    assert post.removal_source.value == "owner"
    assert post.removed_at is not None
    for model in (InsightPublication, PostLike, Bookmark, Comment):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0, model
    actions = (
        await db_session.scalars(select(ModerationAction).order_by(ModerationAction.id))
    ).all()
    assert [(a.action.value, a.source.value) for a in actions] == [
        ("published", "guard"),
        ("withdrawn", "owner"),
    ]


async def test_a_draft_is_withdrawn_the_same_way(make_member, make_insight, db_session):
    author = await make_member("author")
    post_id = (await create(author, make_insight(author))).json()["id"]

    assert (await author.http.delete(f"/posts/{post_id}")).status_code == 204
    assert (await author.http.get(f"/posts/{post_id}")).status_code == 410


async def test_only_the_author_withdraws_a_post_and_an_unknown_one_is_a_404(
    make_member, make_insight, guard
):
    author = await make_member("author")
    other = await make_member("other")
    guest = await make_member(signed_in=False)
    post_id = await published(author, make_insight)

    assert (await other.http.delete(f"/posts/{post_id}")).status_code == 404
    assert (await guest.http.delete(f"/posts/{post_id}")).status_code == 401
    assert (await author.http.delete(f"/posts/{any_id()}")).status_code == 404
    assert (await author.http.get(f"/posts/{post_id}")).status_code == 200


async def test_a_post_a_moderator_removed_is_410_to_all_but_a_followers_post_stays_404_to_strangers(
    make_member, make_insight, guard, db_session
):
    from src.services import moderation_service

    author = await make_member("author")
    stranger = await make_member("stranger")
    public_id = await published(author, make_insight)
    private_id = await published(author, make_insight, visibility="followers")
    for post_id in (public_id, private_id):
        post = await db_session.get(Post, int(post_id))
        await moderation_service.remove(db_session, post, MODERATOR, "abuse")
    await db_session.flush()

    assert (await stranger.http.get(f"/posts/{public_id}")).status_code == 410
    assert (await author.http.get(f"/posts/{public_id}")).status_code == 410
    assert (await stranger.http.get(f"/posts/{private_id}")).status_code == 404
    mine = (await author.http.get("/me/posts")).json()["items"]
    assert {item["status"] for item in mine} == {"removed"}
    assert mine[0]["status_message"] == "لم يُقبل لأنه يخالف قواعد المجتمع: إساءة أو مضايقة."


# ─── The author's own list ────────────────────────────────────────────────────


async def test_my_posts_lists_every_state_newest_first_in_pages_and_never_a_withdrawn_one(
    make_member, make_insight, guard
):
    author = await make_member("author")
    other = await make_member("other")
    ids = [(await create(author, make_insight(author))).json()["id"] for _ in range(3)]
    await author.http.post(f"/posts/{ids[0]}/submit")
    await author.http.delete(f"/posts/{ids[1]}")
    await create(other, make_insight(other))

    first = (await author.http.get("/me/posts", params={"limit": 1})).json()
    second = (
        await author.http.get("/me/posts", params={"limit": 1, "cursor": first["next_cursor"]})
    ).json()

    assert [item["id"] for item in first["items"]] == [ids[2]]
    assert [item["id"] for item in second["items"]] == [ids[0]]
    assert second["next_cursor"] is None
    assert first["items"][0]["status"] == "draft"
    assert second["items"][0]["status"] == "published"


async def test_my_posts_needs_a_session_and_refuses_a_forged_cursor(make_member):
    author = await make_member("author")
    guest = await make_member(signed_in=False)

    assert (await guest.http.get("/me/posts")).status_code == 401
    bad = await author.http.get("/me/posts", params={"cursor": "not-a-cursor"})
    assert (bad.status_code, bad.json()["error"]) == (400, "INVALID_CURSOR")


async def test_the_visibility_values_are_the_two_of_the_decision():
    assert {v.value for v in PostVisibility} == {"public", "followers"}
    assert {s.value for s in PostStatus} == {
        "draft",
        "pending_review",
        "published",
        "rejected",
        "removed",
    }


# ─── What the author is told ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "reason", "message"),
    [
        ("draft", None, None),
        ("published", None, None),
        (
            "pending_review",
            "guard_unavailable",
            "تعذّرت المراجعة الآلية الآن، فسيراجعه مشرف قبل نشره.",
        ),
        ("pending_review", "guard_uncertain", "يحتاج إلى مراجعة مشرف قبل نشره."),
        ("pending_review", "reported", "وصلتنا عنه بلاغات، فأُخفي مؤقتًا حتى يراجعه مشرف."),
        ("pending_review", "anything else", "يحتاج إلى مراجعة مشرف قبل نشره."),
        ("pending_review", None, "يحتاج إلى مراجعة مشرف قبل نشره."),
        ("rejected", "self_harm", "لم يُقبل لأنه يخالف قواعد المجتمع: إيذاء النفس."),
        (
            "removed",
            "false_religious_claim",
            "لم يُقبل لأنه يخالف قواعد المجتمع: نسبة قول ديني إلى غير قائله.",
        ),
        ("rejected", "a moderator's private words", "لم يُقبل لأنه يخالف قواعد المجتمع."),
        ("removed", None, "لم يُقبل لأنه يخالف قواعد المجتمع."),
    ],
)
def test_the_outcome_message_says_what_happened_and_never_repeats_a_raw_reason(
    status, reason, message
):
    assert outcome_message(status, reason) == message
