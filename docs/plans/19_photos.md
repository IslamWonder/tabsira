# 19 · Consented photos

**Phase:** 2 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-06 07:10 (Tunis)

The photo of a scan, kept with its owner's consent, shown to the public only by the owner's choice (v2 §15 and §19, decisions 8 and 44).

| Step                                     | Status | Notes                                                                                                   |
| ---------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------- |
| Photo rules and the two stores           | ✅     | `src/storage/photos.py` (`PhotoFacts`, `PhotoStore`), local disk and S3, probed at start (decision 44). |
| Keep at «تمّ», publish, withdraw, delete | ✅     | Task 19.1: `services/photo_service.py`; keys on `insights`, a `with_photo` flag on `map_entries`.       |
| Show the public copy on the web          | ✅     | Task 19.2: `photo_url` on a public post and a published entry, «أرفق الصورة» on both publish screens.   |

**How we check it**

- Nothing is kept for a guest, an under-13 account, a sensitive scene, a withdrawn consent or a switched-off feature (tested, `tests/scans/test_photo_keep.py`).
- The public copy exists exactly while a public post or a published map entry shows it; withdrawal, re-placing, a hold by reports, a moderator's removal or refusal and a withdrawn consent delete it (tested, `tests/test_photo_publication.py`); a deletion the store refused is reconciled by the worker and an hourly timer (tested, `tests/test_photo_reconcile.py`).
- Deleting the account or the consent deletes both copies; a store that cannot be reached refuses the act with 503 (tested, `tests/test_account_photos.py`).
- No response carries a storage key; the export says only which insights have a photo.
- A storage key is in no public schema (tested, `test_atlas.py`, `test_social_posts.py`); the address is given only by a published public post or a published entry that shows the photo, and the local `/media` route serves the `public/` prefix alone (tested, `tests/test_photo_publication.py`).

## Tasks

### 19.1 Consented photo flow

- **Status:** ✅ 2026-10-04 21:21, owners' agent (branch task/19.1-consented-photos)
- **Goal:** Close the first three rows of the wave 4 compliance audit: the photo rules and the store existed but nothing called them.
- **Depends on:** 16.1, 17.1
- **Touches:** apps/api/src/services/{photo_service,completion_service,publication_service,insight_table_source,post_service,atlas_service,moderation_service,account_service,profile_service}.py, routers/{insights,posts,atlas,account,profile}.py, schemas/{social,atlas,account}.py, models/{scan,atlas}.py, admin/views/moderation.py, two app migrations (`20261004_207000`, `20261004_208000`), their tests, the generated web client, apps/web/src/messages/legal.ts, docs/PRIVACY.md, docs/SOCIAL_NETWORK.md.
- **Done when:** A consenting account's first «تمّ» keeps the photo; publishing with the choice makes the public copy; withdrawal, removal, consent withdrawal and account deletion remove it; the terms say exactly that.
- **What was built:** `PhotoStoreDep` (built once per application from the settings, a test sets `app.state.photo_store`). «تمّ» re-encodes the buffer copy (upright, 2560 px, no metadata) into the private store under the rules of `PhotoFacts`; the buffer keeps its hour. `POST /posts` and `PUT /insights/{id}/map` take `photo: false|true`; the one public copy per insight is made by `sync_public_copy` on publication (public posts and map entries only, rules checked again) and deleted when the last one showing it goes, by the owner or a moderator, or when the rules no longer hold. `GET /account/export` lists `learning.photos` (insight id, published) and `DELETE /account`, a withdrawn photo consent and declaring under 13 delete both copies, refusing with 503 `STORAGE_UNAVAILABLE` when the store is down. Also, as the coordinator asked: creating a post and placing a map entry answer 409 `UNDER_13_CANNOT_PUBLISH` for an account that said it is under 13.
- **Reviews:** privacy self-review against `.claude/agents/privacy-security-reviewer.md` (the agent could not be launched from this session): fixed in the same branch so that a followers-only post never makes a copy under the world-readable `public/` prefix; logs name an insight id only; no key in any response.
- **Left for the owners:** production needs the S3 bucket (`STORAGE_BACKEND=s3`, `S3_*`, `S3_PUBLIC_BASE_URL`, a bucket policy or CDN that serves `public/*` and nothing else); no web control offers the photo choice yet and no public response carries the copy's address (follow-up); `has_photo` on a post states the owner's choice, not whether a copy exists now; the legal text was clarified without a version bump (no promise weakened; the owners may decide otherwise).

### 19.2 The photo on the web

- **Status:** ✅ 2026-10-04 21:52, owners' agent (branch task/19.2-photo-web)
- **Goal:** Close the last row: let the owner choose the photo on the publish screens and show the public copy where they chose to show it.
- **Depends on:** 19.1
- **Touches:** apps/api/src/{services/{photo_service,post_view,atlas_service,insight_view}.py, routers/{posts,feed,reactions,atlas,media}.py, schemas/{social,atlas,insight}.py, main.py}, their tests, the generated web client, apps/web/src/{components/ui/checkbox-field.tsx, lib/scan/kept-photo.ts, social/api.ts, components/community/{publish-screen,post-card,public-photo}.tsx, components/atlas/{map-publish-screen,entry-screen}.tsx, messages/{ar,legal}.ts, test fixtures}, docs/PRIVACY.md, docs/SOCIAL_NETWORK.md.
- **Done when:** A kept photo can be chosen on both publish screens, off by default; a published public post and a published entry carry `photo_url` and the pages show it; nothing else names the copy; the terms say so.
- **What was built:** `InsightOut.photo_url` (published public posts only, even when a map entry made the copy; drafts, held posts and followers-only posts say null), `AtlasEntryOut.photo_url` (entries whose owner chose the photo), `InsightImageOut.has_photo` on the owner's own insight view. The address comes from the store (`S3_PUBLIC_BASE_URL`, or the API's new `GET /media/public/<id>.jpg` on the local disk, `Cache-Control: public, max-age=300`, 404 under S3 and for anything but a public key). The web asks the owner's insight view for `has_photo` and offers «أرفق الصورة» (a native checkbox, unticked, one line saying the photo becomes public) on both publish screens; the post offers it for a public audience only. The post page and the entry page render a plain lazy `<img>` from `photo_url` when it is http(s), with a fixed Arabic alt naming the title; feed cards and the share card show no photo.
- **Reviews:** privacy self-review (no reviewer subagent available in this session): no key in any response (schema guard tests extended), a followers-only post never names the copy a map entry made, the media route checks the key's shape before touching the disk and serves `public/` alone.
- **Left for the owners:** the new public route `GET /media/public/*` on the API was added without asking first (the brief named "the local media route", which did not exist); the legal text changed without a version bump (the public copy was already described as made by the owner's choice; only the "not shown yet" sentence changed), to confirm (decision 35); the photo cannot be added to or removed from an existing post afterwards (`PATCH /posts` has no `photo`), only chosen when the draft is made.

### 19.3 Privacy review fixes of the photo flow

- **Status:** ✅ 2026-10-04 22:06, owners' agent (branch task/19.3-photo-review-fixes)
- **Goal:** Close the four findings of the privacy review of task 19.1 (`../tabsira-artifact/reviews/privacy-review-19.1-photos-2026-10-04.md`): a `public/` copy must never outlive what shows it, and the export must carry no key.
- **Depends on:** 19.1, 19.2
- **Touches:** apps/api/src/{services/{photo_service,photo_reconcile,atlas_service,moderation_service,report_service,social_export}.py, routers/{atlas,reports}.py, admin/views/moderation.py, schemas/social_export.py, worker.py, cli/reconcile_photos.py}, their tests, deploy/systemd (one timer), deploy/apply-config.sh, docs/{PRIVACY,OPERATIONS}.md.
- **Done when:** Re-placing a published entry, a hold by reports and a rejection after a hold delete the copy; a deletion the store refused is retried in one process; the export states a post's photo as `has_photo`/`published` only.
- **What was built:** `place()` takes the store and syncs after the flush; `hold_if_reported` and `reject` take `photos` and sync (the report route and the admin view pass it). `sync_public_copy` returns whether the store did its part and, on a failure, asks the worker (`photos.reconcile`, run 30 s later in that one process) to run `photo_service.reconcile_public_copies`, which deletes every public copy nothing shows any more under an advisory lock; `tabsira-reconcile-photos.timer` runs `python -m src.cli.reconcile_photos` hourly. The person still gets 204. `PublicationExport.photo_ref` is replaced by `has_photo` and `published`.
- **Reviews:** the four findings and the missing tests the review named are covered by `tests/test_photo_publication.py` and `tests/test_photo_reconcile.py`; no new setting.
- **Left for the owners:** the privacy text's wording (`legal.ts`) was not changed: it already promises the deletion that now holds; the review's note on a legal version bump stays theirs to decide.

### 19.4 Enable the photo reconcile timer in the host configuration

- **Status:** ⬜ open
- **Goal:** `deploy/apply-config.sh` must enable `tabsira-reconcile-photos.timer` next to the two other timers (`systemctl enable --now ... tabsira-reconcile-photos.timer`). Task 19.3 installed the unit and the timer files but left this one line out, because the main checkout held uncommitted edits to `deploy/apply-config.sh` at merge time and they were not to be overwritten.
- **Depends on:** 19.3
- **Touches:** deploy/apply-config.sh (one line), docs/OPERATIONS.md if the wording changes.
- **Done when:** a fresh `apply-config.sh` run enables the timer; `systemctl list-timers` on the host shows it.

### 19.5 One private folder per account

- **Status:** ✅ 2026-10-05, owners' request (following the earlier prototype's per-user folders)
- **Goal:** keep each account's private copies under `private/users/<account id>/insights/`, so one person's photos can be exported or deleted together; published copies keep names that never name the account. Deleting the account or withdrawing the photo consent removes each photo by its row and then empties the folder, and the folder is swept once more after the deletion commits. The start-up probe proves the keys can list and batch-delete a folder.
- **Touches:** apps/api/src/storage/{base,local,s3,photos,probe}.py, services/{photo_service,account_service}.py, routers/account.py, models/scan.py, one app migration (`20261005_150000`, `photo_key` 64 → 128), the privacy text (version 2026-10-05T15:00Z: the photo provider sees the account id in private copies' names), docs/PRIVACY.md, docs/OPERATIONS.md, their tests.
- **Done when:** a privacy review passes; deletion and withdrawal leave no object in the folder; the probe fails without `s3:ListBucket`.
- **Not yet:** the account export lists the kept photos without the images; a download of the folder (signed links, or a zip) is the next step.
