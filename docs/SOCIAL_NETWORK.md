# «تبصرة تواصل»: the social network

What the API does for the social network, and where each piece plugs in. Scope is decision 2: posts made from verified insights, the feeds «لك» and «أتابع» with cursors, follow, like, comments, bookmark, report, block and moderation states. There are no reposts, polls, mentions, push notifications or direct messages. Code: `apps/api/src/routers/{members,posts,reactions,comments,reports,feed}.py`, services of the same names in `apps/api/src/services`, models in `models/social.py` and `models/moderation.py`. What is stored and why is in `docs/PRIVACY.md`.

The whole network sits behind `FEATURE_SOCIAL`: with it off every route below answers 404 and its sitemap sections are not advertised.

## Ids and people

- A post, a comment, a publication and a report take a public id (decision 37): a 64-bit, time-ordered number from `app.timestamp_id(table)`. JSON carries it as a string; a path takes a positive number up to 2^63 - 1, and a larger one is a 422.
- An account keeps its UUID inside the API. It never appears in a path or a public response: people are addressed by **handle**. Knowing an id, of a post or of anything else, grants nothing; every route checks session, owner, state, audience and blocks.
- **Public identity.** A person who publishes chooses a handle (`/u/<handle>`) and a public name with `PUT /me/public-identity`, and needs a verified address to do it. The account's own display name may be a real name or the one Google gave, so it is never used. A handle is 3 to 30 Latin or Arabic letters (no diacritics, no tatweel), digits and underscores, starting with a letter, unique whatever its case (`409 HANDLE_TAKEN`), and not a reserved name or one that starts like the platform or its staff (`tabsira…`, `admin…`, `support…`, `moderator…`, `تبصر…`, `مشرف…`, `إدارة…`). A public name is 1 to 40 characters with no control characters, address or link. Until both are set, posting and commenting answer `409 PUBLIC_IDENTITY_REQUIRED`.
- **Public profile**, `GET /u/{handle}`: handle, public name, the month joined, and three counts (published public posts, followers, following), read from the rows they count. Never an e-mail address, the account's own name, a profile answer or a place. A profile behind a block answers 404, as a missing one does.

## From an insight to a post

1. `POST /posts {insight_id, reflection?, visibility}` reads one of the caller's own insights through the **`InsightSource`** (below), checks it, copies it into an immutable **publication** and opens a **draft** on it. Nothing is visible to anyone else.
2. `PATCH /posts/{id}` edits a draft or a refused post (which becomes a draft again). A post waiting for review or published is not editable.
3. `POST /posts/{id}/submit` runs the guard (below): `published`, `rejected` with its reason, or `pending_review`. The answer carries the outcome in Arabic for the author.
4. `DELETE /posts/{id}` withdraws a post, draft or published. Its reflection, publication, comments, likes and bookmarks are erased; the address answers **410 Gone** from then on, for everyone who could have read it and on every route (an id that was never public, a draft or a post removed before it was published, answers 404 to everyone but its author, so an id never says that something once existed), and the post leaves every feed, profile and sitemap. A post a moderator removes keeps its content (for an appeal) and answers 410 to everyone but the moderators; its author sees it in `GET /me/posts` with the reason.

`GET /posts/{id}` answers 404 for what the caller may not see (a draft, a post held or refused, a followers-only post of someone the caller does not follow, a post behind a block, a post of a disabled account), so an id reveals nothing. `visibility` is `public` or `followers`; following needs no approval, so «المتابعون» means whoever follows.

The five states are `draft`, `pending_review`, `published`, `rejected` and `removed`. Only the author sees a state other than `published`, and why.

### The publication

`app.insight_publications` is made once, from the insight as it is at that moment, and the database refuses every UPDATE (a trigger). It holds the title, the glimpse, the relation type, the concepts, the explanation excerpt, the small step, the insight's id and version, and **references** to the evidence: `{surah, ayah}` and `{collection, number}`. It never holds scripture. A reader's response reads the verse and the hadith from the scripture store by reference, byte for byte as stored, with the stored hash, a quranpedia link and, for a hadith, the dorar.net ruling and the «تحقق في الدرر» link (`services/evidence_view.py`). A hadith is shown only while the ruling in force is صحيح or حسن; if that changes, the post shows the verse alone.

What is checked at publish time, whatever the source says: the insight is the caller's and verified; every text fits its limit and none looks like scripture (the leak guard); the evidence exists in the store, at most three of each kind, and every hadith is eligible; and the photo reference is kept **only** if its owner consented to publish it, the scene is not sensitive and the photo rules of section 19 still allow it (`PhotoFacts.refusal`, checked again because facts change: the feature is on, the account has not since said it is under 13, and it still agrees to keep photos).

### The author's own words

`reflection` is the author's text, in its own field and its own object in the response: `{text, source: "user", verified: false, looks_like_scripture}`. It is never shown with the verified badge, whatever it says; text that reads like Quran or hadith is allowed as the author's own words and is flagged so the client can label it.

### Where the insights plug in: `InsightSource`

The insights table is built elsewhere. The social network reads it through one protocol, `src/services/insight_source.py`:

```python
class InsightSource(Protocol):
    async def load_for_publishing(
        self, db: AsyncSession, insight_id: int, owner_id: uuid.UUID
    ) -> InsightSnapshot | None: ...
```

It returns an `InsightSnapshot` (id, version, owner, verified, title, glimpse, relation type, explanation excerpt, evidence references, step, concepts, and the photo reference with `photo_consent` and `scene_sensitive`), or `None` for an insight that does not exist or is not the owner's. `services/insight_table_source.py` implements it over `app.insights` and `create_app` uses it unless a test hands in a double (`FakeInsightSource` in `tests/support_social.py`); an application built with no source at all answers `503 SERVICE_UNAVAILABLE` and invents nothing.

A second plug point is the **photo**: a publication keeps the private reference of the owner's photo (`photo_ref`), for the owner and for the photo store; **no public response carries it**, they say only `has_photo`. Turning it into a public address (copying the photo to its public place when its owner publishes, and removing it when the post is withdrawn) belongs to the photo store, not to this module. The sitemap lists no image until that address exists.

## Reactions

- **Like** («أثر»): `PUT` and `DELETE /posts/{id}/like`, one per account and post, safe to repeat, answers the state and the count. Who liked is never listed.
- **Bookmark**: `PUT` and `DELETE /posts/{id}/bookmark` (204), and `GET /me/bookmarks`. Private: nobody sees whose a bookmark is, and no response counts them.
- **Follow**: `PUT` and `DELETE /u/{handle}/follow`. Nobody follows themselves.
- Counts are never stored on the post: likes and comments are counted from their rows for each page of a feed in a fixed number of queries, so a count cannot drift.

## Comments

`GET /posts/{id}/comments` (oldest first, cursor), `POST /posts/{id}/comments {body, parent_id?}`, `DELETE /posts/{id}/comments/{comment_id}` (the author's own; replies go with it). A thread is one level deep: a reply answers a comment that is not itself a reply, and a comment takes at most 50 replies. A new comment is judged by the guard before anyone but its author sees it. A person can delete their own comment at any time, even after they can no longer read the post (they unfollowed its author, or blocked them). A comment by someone the viewer blocked or who blocked the viewer is not in the viewer's thread, and a comment by someone the post's author blocked is gone for everyone; an unblock brings it back.

## Blocks

`PUT` and `DELETE /blocks/{handle}`, `GET /blocks`. A block hides each of the two from the other everywhere (feeds, profiles, posts, comments, follow lists, bookmarks) and ends the follows between them in both directions; the person blocked is answered with 404, as for something that does not exist. Only the blocker lifts it.

## Feeds

All three page by an opaque cursor and take `limit` (1 to 50, default 20). A page that is empty on the first request says why in `empty_reason`; no post is ever invented to fill a feed.

| Route                   | Needs   | What it lists                                                                                                                                                          |
| ----------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /feed/following`   | session | «أتابع»: posts of the members the caller follows (followers-only ones included), newest first by `(published_at, id)`. `empty_reason`: `follows_nobody` or `no_posts`. |
| `GET /feed/for-you`     | nothing | «لك»: the newest readable posts, ranked, each with `why` («لماذا أرى هذا؟»).                                                                                           |
| `GET /feed/latest`      | nothing | Every public post, newest first by `(published_at, id)`.                                                                                                               |
| `GET /u/{handle}/posts` | nothing | A member's published posts the caller may read, newest first.                                                                                                          |

The cursor of the chronological feeds is the `(published_at, id)` of the last item, so a post published or withdrawn between two pages neither repeats nor skips an item.

### How «لك» ranks

`services/ranking.py`, pure arithmetic with four inputs, each one told to the reader: **freshness** (halves every 24 hours), **follows** (+0.5 for an author the reader follows), **variety** (each earlier post in the list on the same concept lowers a post by 0.15, up to 0.6) and **already met** (-0.8 for a post the reader liked, saved or commented on). It never uses religion, age, gender or any profile answer, learns nothing from clicks, and uses no model. A reader who switches personalisation off (`POST /consents`, kind `personalization`) and a guest get freshness and variety only. The 200 newest readable posts are ranked; the cursor pins the moment of ranking and the score of the last item, so the next page continues the list that was computed.

`why` is one of `followed_author` («لأنك تتابع …»), `fresh`, `new_topic` and `community`. When the learner's insight exposures (decision 13) exist, `feed_service.seen_post_ids` is where a post about an insight the learner has already been shown is added to "already met".

## Moderation

Every post (its reflection) and every comment goes through the **guard** first (`services/moderation_guard.py`): OpenAI's `omni-moderation-latest` through the model client of `src/ai`, sent the text and nothing else, never who wrote it.

- Nothing flagged and every score under `SOCIAL_GUARD_ALLOW_SCORE` (0.4): published.
- A category the provider flagged at `SOCIAL_GUARD_REJECT_SCORE` (0.85) or over, or a flag on `sexual/minors`: `rejected`, with the category as the reason.
- Anything between: `pending_review`, for a moderator.
- **It fails closed.** No key, a timeout, an error, an answer in the wrong shape: `pending_review` with `guard_unavailable`, never published.
- A post with no reflection has no words of the author to judge and is published by the guard rule `no_user_text`; everything else in it is the platform's verified content.

The author is told the outcome by `status`, `status_reason` (only a code the app defines) and `status_message` (Arabic) on their own copy, in the answer to `submit` or `comments` and in `GET /me/posts`. A moderator's own free words are never returned.

**Moderators** (the admin area calls these functions, it has no routes of its own here): `moderation_service.approve`, `reject` and `remove` for a post or a comment. Each locks the item, reads it fresh and applies only from the states it is for: `approve` from held, refused or moderator-removed, `reject` from held, `remove` from published; a draft, and a post its author withdrew, are refused with a 409. Each logs one row in `app.moderation_actions` and closes the open reports on the item (dismissed by an approval, actioned by a rejection or removal). The log is a TimescaleDB hypertable on `at`, append-only (a trigger refuses UPDATE and DELETE), compressed after `MODERATION_LOG_COMPRESS_AFTER_DAYS` and dropped after `MODERATION_LOG_RETENTION_DAYS`. A row holds the target, the action, the source (`guard`, `moderator`, `reports`, `owner`), the reason code and the guard's flagged categories and rounded scores; never the text, never the author.

**Reports**: `POST /reports {target_type, target_id, reason, details?}` with the reasons `abuse`, `spam`, `false_religious_claim`, `unauthorised_photo`, `wrong_place` («المكان غير صحيح»), `private_information` («الموقع أو الصورة يكشفان معلومات خاصة») and `other`; the two place reasons are for the atlas, which will report its own entries into the same table. Only what the reporter may read can be reported, not their own words, and the same thing twice answers with the first report. When `SOCIAL_REPORT_HOLD_THRESHOLD` (3, 0 turns it off) different accounts have an open report on a published item, it returns to the queue as `pending_review` with the reason `reported`, hidden until a moderator decides.

## Limits

Every write has a budget per account and one over all accounts, counted in memory by the shared window limiter (`services/social_limits.py`): identity 5 an hour, posts 20 an hour, comments 15 in ten minutes, reactions 120 a minute, reports 10 an hour, blocks 30 an hour. A refusal is `429 RATE_LIMITED` with `Retry-After`. The numbers bound spam and a runaway client; with N workers the ceiling is N times higher. Responses of every route of the network carry `Cache-Control: no-store`, since they say what the viewer liked, saved and follows.

## Account export and deletion

`GET /account/export` includes a `social` object: the posts with their reflections and publications, the comments, the members followed and blocked (by handle only), the likes and bookmarks, and the reports filed. `DELETE /account` removes all of it by cascade, and the posts, comments, follows and reactions with it; what is left is the moderation log, which names no author and holds no text.

## The web screens

`apps/web/src/components/community` and `apps/web/src/social` (task 16.1). The feeds at `/community` («لك», «أتابع», the latest, and for a signed-in person «منشوراتي» in every state and «محفوظاتي»), each with its cursor behind a «اعرض المزيد» button and, in «لك», the item's reason behind «لماذا أرى هذا؟»; a post at `/posts/<id>` with its comments and one level of replies; a public profile at `/u/<handle>` with follow and block; publishing at `/community/publish?insight=<id>` (draft, preview, submit, edit a refused post, withdraw); and in «ملفي» the public handle and name with the list of blocked members. The web never decides a permission: it tells the viewer which step the API will ask for (sign in, a verified address, a public identity) and shows the API's answer. Scripture is shown by the shared evidence card exactly as the API returns it, and the author's reflection is labelled as the author's words. The screens are reached only while `FEATURE_SOCIAL` is on; with it off the API answers 404 and the feeds say they cannot be loaded.

The insights plug in through `services/insight_table_source.py`, the `InsightSource` over `app.insights`: an insight is publishable when it is the caller's own and came out of the real pipeline (`engine = "pipeline"`); a demo insight and a prepared tutorial copy are not.

## Sitemap

`services/social_sitemap.py` registers the `posts` and `profiles` sections of the sitemap (decision 29). A post is listed while it is published, public and its author's account is active; a profile when its member has a handle and at least one such post. Both are paged by id, oldest first. A post's `lastmod` is its own `updated_at`; a profile's is the time of its newest public post, never the account's own updated time, which moves when a password or an address changes. A post whose publication is gone is never listed, and a withdrawn, removed, held or followers-only post leaves the list at once. The paths are `/posts/<id>` and `/u/<percent-encoded handle>`.

## Settings

`SOCIAL_GUARD_TIMEOUT_SECONDS`, `SOCIAL_GUARD_ALLOW_SCORE`, `SOCIAL_GUARD_REJECT_SCORE`, `SOCIAL_REPORT_HOLD_THRESHOLD`, `MODERATION_LOG_RETENTION_DAYS`, `MODERATION_LOG_COMPRESS_AFTER_DAYS`, and the existing `FEATURE_SOCIAL` and `AI_OPENAI__*`.

## Not built

A follow request that the followee approves; a moderators' queue screen and routes (the admin area's views call the `moderation_service` functions); notifications of any kind (the author reads the outcome on their own copy); an appeal; search; a handle history that holds a released handle back; a list of a member's followers or of the members they follow; mutes and keyword filters; the public copy of a photo (published when the post is published, removed when it is withdrawn or the account is deleted), which the photo store provides and nothing here calls yet; limits on the budget over all accounts that a set of verified accounts could use up; a hold-back of a released handle; an erase of the reflection of a post a moderator removed before the account goes.
