# 16 · Social network «تبصرة تواصل»

**Phase:** 2 · **Priority:** Medium · **Status:** ✅ · **Updated:** 2026-10-06 07:10 (Tunis)

Posts made from verified insights, follows, likes, comments, reports and moderation.

| Step                                                               | Status | Notes                                                                                                                                                                                                    |
| ------------------------------------------------------------------ | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Server side: profiles, posts, feeds, comments, reports, moderation | ✅     | Merged, switched off in production.                                                                                                                                                                      |
| Screens                                                            | ✅     | Task 16.1, screenshots in docs/screenshots (community, post, profile, publish).                                                                                                                          |
| Moderators' queue                                                  | ✅     | Admin queue for posts and comments (task 12.2) and map entries (task 17.2).                                                                                                                              |
| Privacy re-review                                                  | ✅     | Passed for social on 2026-10-04 (`../tabsira-artifact/reviews/privacy-re-review-social-atlas-2026-10-04.md`); its atlas findings 2-7 are task 17.3, finding 1 task 17.2.                                 |
| Share a profile, own page in the top bar                           | ✅     | «شارك صفحتك» on the public profile and in «ملفي» (the phone's share dialog, else the link copied); «صفحتي» in the top bar once a handle is chosen (2026-10-05).                                          |
| Follow from a post or a public insight                             | ✅     | A quiet «تابع» beside the author on every post (the API says `follows_author`, one query per page) and on a public insight's page; always the reader's own tap, never a follow by visiting (2026-10-05). |

**How we check it**

- Re-review before it is switched on.

## Tasks

### 16.1 Social screens

- **Status:** ✅ 2026-10-04 16:51, owners' Wave 4 agent
- **Goal:** Feeds, posts, profiles, comments, reports.
- **Depends on:** Phase 2.
- **Touches:** apps/web community routes.
- **Done when:** Privacy re-review first.

### 16.2 Community summary on the home page

- **Status:** ✅ 2026-10-05 18:43 (Tunis)
- **Goal:** A quiet «مجتمع تبصرة» card that tells a visitor how large the community is: members and their countries, published insights, entries on the atlas, entries waiting for a sponsor, with one link to the feed or the atlas.
- **Depends on:** 16.1, 17 (atlas), 21 (sponsoring).
- **Touches:** `GET /community/summary` (public, aggregate counts of public things only, `null` for a feature that is off, kept ten minutes per worker, 503 when the database is down); `apps/web/src/components/landing/community-summary.tsx`, rendered by the home page on the server with a ten-minute revalidation, after the steps so it is never on a phone's first screen beside the capture (decision 62).
- **Done when:** the card is hidden when the API fails or members are under 50; the counts carry no person, place or id (`docs/PRIVACY.md`).

### 16.3 Views of a post

- **Status:** ✅ 2026-10-06 00:45 (Tunis)
- **Goal:** Show how many people viewed a post, counted the way the earlier prototype counts post views.
- **Depends on:** 16.1.
- **Touches:** `apps/api/src/services/view_service.py`, `POST /posts/{id}/view` in `routers/posts.py`, `PostOut.views_count`, `Post.views_count` and migration `20261005_233000`; `apps/web/src/components/community/{post-screen,post-card}.tsx`, `src/social/api.ts`, the messages, the generated client; the privacy page (version 2026-10-06T00:00Z), `docs/PRIVACY.md`, `docs/SOCIAL_NETWORK.md`; the mock data generator and `import_mock` (task 23).
- **Done when:** a view counts once per viewer a day (account and address, one Redis transaction), never the signed-in author's (their opening marks their address; no session is looked up, so the count never reveals an author's address) nor a bot's, and never from reading alone; who viewed is stored nowhere, the Redis marks are HMAC keys that name nobody and expire after 24 hours; 300 views an hour per address and 3000 per IPv6 /48, checked before anything is looked up, and no overall budget; the count shows on every published post card; tests in the same commits.
- **Reviews:** privacy review before merge: its two blocking findings (the author-address look-up told a neighbour who wrote a post, and the account id in the Redis keys contradicted the privacy text) and its other findings (rate limit, atomic check, wording and date of the privacy page) are fixed; its re-review passed, and its four low points (the limit ran after the session look-up, an overall budget a flood could exhaust, two sentences of the docs) are fixed too.
- **Production `.env`:** no new key. `PRIVACY_VERSION`, if the file sets it, must become `2026-10-06T00:00Z` (or be removed so the code's value applies).

### 16.4 One post per basira, published by default (decision 68)

- **Status:** ✅ 2026-10-06 (Tunis)
- **Goal:** a published basira is in its owner's publications: sharing, publishing in «تواصل» and placing on the atlas lead to its one post; the atlas is an extra choice; basiras published before get their post once.
- **Touches:** `apps/api/src/services/insight_post_service.py`, `PUT /insights/{id}/post` and the one-post rule of `POST /posts` in `routers/posts.py`, `ErrorCode.INSIGHT_ALREADY_POSTED`, `apps/api/src/cli/publish_missing_posts.py`, the `posts` mock fill-in; `apps/web/src/components/insight/{publication,use-quick-share,share-sheet,completion-panel,insight-screen}`, `components/atlas/map-publish-screen.tsx`, `components/community/publish-screen.tsx`, their pages, the messages, the privacy page (version 2026-10-06T17:00Z), `docs/{PRIVACY,SOCIAL_NETWORK,OPERATIONS}.md`, `tools/mockdata/README.md`.
- **Done when:** no insight gets a second live post; the map screen offers «انشرها أيضًا في تواصل» ticked and posts only once the entry is shown; a published post offers «ضعها أيضًا على الخريطة»; the backfill skips orphaned entries, withdrawals, closed or unverified accounts and accounts with no handle, and counts them; tests in the same commits; privacy review before merge.
- **Production `.env`:** no new key. `PRIVACY_VERSION`, if the file sets it, must become `2026-10-06T17:00Z` (or be removed so the code's value applies).
- **To apply:** after deploying, `cd apps/api && uv run python -m src.cli.publish_missing_posts --dry-run --i-understand --allow-production` to count, then the same without `--dry-run`.
