# 19 · Consented photos

**Phase:** 2 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-04 21:21 (Tunis)

The photo of a scan, kept with its owner's consent, shown to the public only by the owner's choice (v2 §15 and §19, decisions 8 and 44).

| Step                                     | Status | Notes                                                                                                   |
| ---------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------- |
| Photo rules and the two stores           | ✅     | `src/storage/photos.py` (`PhotoFacts`, `PhotoStore`), local disk and S3, probed at start (decision 44). |
| Keep at «تمّ», publish, withdraw, delete | ✅     | Task 19.1: `services/photo_service.py`; keys on `insights`, a `with_photo` flag on `map_entries`.       |
| Show the public copy on the web          | ⬜     | No public response carries an address yet; the web has no photo control on the publish screens.         |

**How we check it**

- Nothing is kept for a guest, an under-13 account, a sensitive scene, a withdrawn consent or a switched-off feature (tested, `tests/scans/test_photo_keep.py`).
- The public copy exists exactly while a public post or a published map entry shows it; withdrawal, a moderator's removal and a withdrawn consent delete it (tested, `tests/test_photo_publication.py`).
- Deleting the account or the consent deletes both copies; a store that cannot be reached refuses the act with 503 (tested, `tests/test_account_photos.py`).
- No response carries a storage key; the export says only which insights have a photo.

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
