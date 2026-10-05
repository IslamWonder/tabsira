# 21 · An Islamic spirit for «تبصرة تواصل»

**Phase:** 2 · **Priority:** Medium · **Status:** ⬜ · **Updated:** 2026-10-05 11:43 (Tunis)

The social network leans on acts with a meaning in Islam: sponsoring an insight nobody looks after (decision 60), giving an insight as a gift, and reactions that say something (decision 61).

| Step                                          | Status | Notes                                                  |
| --------------------------------------------- | ------ | ------------------------------------------------------ |
| One feature switchboard, comments off         | ✅     | Task 21.0. Decision 63.                                |
| «كفالة بصيرة»: orphaned atlas entries         | ✅     | Task 21.1 (server) ✅, 21.2 (screens) ✅. Decision 60. |
| Reactions «انتفعتُ بها» and «جزاك الله خيرًا» | ✅     | Task 21.3. Decision 61.                                |
| «أهدِ بصيرة»: giving an insight               | ⏸      | Task 21.4, a plan only until the owners decide.        |

**How we check it**

- An orphaned entry's public answers carry the widened place and no handle; the earlier cell never reaches a public API again (tested).
- The orphan job run twice on the same day changes nothing the second time (tested).
- No sponsoring, gift or reaction screen shows points, a level or a promise of reward.
- Any verse or hadith on these screens comes from the store by id and matches its hash (tested).

## Tasks

### 21.0 One feature switchboard, comments as their own switch

- **Status:** ✅ done 2026-10-05 09:06 (Tunis)
- **Goal:** `DISABLED_FEATURES` and `ENABLED_FEATURES` replace the `FEATURE_*` keys for the API and the web; `FeatureFlag` names every feature, `atlas_sponsorship` (decision 60) included for task 21.1; `social_comments` and `camera_anchor` are off by default; a child is off while its parent is; a feature that is off answers 404; the old keys are refused at start; comments are off until the owners enable them.
- **Touches:** apps/api/src/{features.py,config.py,deps.py,routers,cli}, apps/web/src/config/server-env.ts and the community components, the generated web client, .env.example, deploy/env.production.example, docs.
- **Done when:** The lists, the parent rule, the legacy-key refusal, `requires` and the 404 of every comment route are tested.
- **Notes:** Decision 63. In production's `.env`, delete every `FEATURE_*` line and set `DISABLED_FEATURES=camera_discovery,dev_inspector` (the social network and the atlas are on).

### 21.1 Orphaned entries and sponsoring, server side

- **Status:** ✅ done 2026-10-05 09:46 (Tunis)
- **Goal:** `MapEntryStatus.ORPHANED`; a "last sign of life" time on the entry (the author's edit or re-placing, a sponsor's reflection, a sponsorship); `python -m src.cli.mark_orphans` for a daily systemd timer on one host, which turns published, unsponsored entries quiet for `ORPHAN_AFTER_DAYS` (30) into `orphaned`, widens their public point to the centre of their admin area (city or region) and drops the handle from public answers; a `map_entry_generalisations` table recording each widening (entry, earlier cell size and label, new level and label, reason, time); `map_entry_sponsorships` (entry, sponsor, started, ended) with one open sponsorship per entry; `POST`/`DELETE /atlas/entries/{id}/sponsorship`; the sponsor's one reflection, moderated like a comment; `GET /atlas/orphans?near=` at the widened places only.
- **Depends on:** 17.3.
- **Touches:** apps/api/src/{models/atlas.py,services/atlas_service.py,routers/atlas.py,cli/mark_orphans.py,config.py}, a migration in the app chain, deploy/ (the timer), .env.example, deploy/env.production.example, the terms and privacy text (widening, sponsor's name shown), docs/PRIVACY.md, the generated web client.
- **Done when:** A widened entry never answers with its earlier cell anywhere; blocks apply to sponsors; an account under 13 cannot sponsor; the job is idempotent.
- **Reviews:** privacy review before merge (location, public identity); decision 42's exception applies, tests in the same commit.
- **Waiting on the owners:** what counts as a sign of life beyond the list above (views do not, so nothing is tracked about readers).
- **What was built:** `MapEntryStatus.ORPHANED`, `map_entries.last_active_at` (set by publishing, the author placing the entry again, a sponsorship starting, the sponsor's reflection; every existing entry starts at the time of the migration, so the quiet period begins at the deploy) and `widened_level`; `ORPHAN_AFTER_DAYS` (30); `python -m src.cli.mark_orphans` under `tabsira-mark-orphans.timer` (daily 04:10 UTC, enabled in `deploy/apply-config.sh`, a hardened unit; a no-op while `atlas` or `atlas_sponsorship` is off). The level is chosen from the area alone, never from the distance to the earlier public point (that would betray it), among levels whose cell is larger than the entry's own: the region (ADM1) of the entry's GeoNames place when it has 100 000 people or more; that place when it is a city of 10 000 or more; the country centre; a fixed grid cell, the first of 50, 100, 200 km and larger that is at least twice the entry's cell. It never reads the capture point. The earlier point, cell and label go to `map_entry_generalisations`, which no route reads and a withdrawal deletes; the author is told the level, label and time (`widened` in their view and export). The entry gets a new public id when widened (the old one is the millisecond it was placed) and the old address answers 410 (`map_entry_retired_ids`; `ON UPDATE CASCADE` on the foreign keys). `atlas_service.place` keeps a widened place whatever the author does (the entry row is locked and read fresh; a sponsored entry cannot be placed again, 409); the handle, the cell polygon, the link to the post and the photo are gone from a widened entry for good. Blocks: a block against the hidden author changes no answer (it would name them); a block against the sponsor hides the entry. Sponsoring: `map_entry_sponsorships`, one row per entry that exists only while the sponsorship does (ending, withdrawal, removal and account deletion delete it, the reflection with it), the five routes below, the reflection judged by the comment guard and refused with 422 when it reads like scripture. The reflection has a public id, can be reported (`target_type` `sponsorship`) and moderated in the queue like a comment, and its verdicts are in the moderation log. A moderator can remove, hold and restore an orphaned entry: a widened entry nobody sponsors comes back `orphaned`, never `published` as the author's. `/atlas/orphans` snaps the position to a 0.05° grid and nginx logs `/atlas/` without the query string. With `atlas_sponsorship` off, orphaned entries are served as plain anonymous widened entries on the map and place pages.
- **Left out, on purpose:** the places sitemap still lists only published entries, so with sponsoring off an orphaned entry's place page is served but not advertised; the author's own post of the same insight keeps naming them (the privacy text says so).

### 21.2 Sponsoring screens

- **Status:** ✅ done 2026-10-05 11:43 (Tunis)
- **Goal:** Orphaned entries suggested on the atlas and the camera discovery («بصيرة تنتظر من يكفلها»), the «اكفل هذه البصيرة» action, «في كفالة فلان» on the entry, the sponsor's reflection, and «كفالاتي» in the member's own entries.
- **Depends on:** 21.1, a design pass recorded in docs/DESIGN_DECISION.md.
- **What 21.1 gives it (all under `atlas_sponsorship`, 404 while off; the generated client has the types):**
  - `GET /atlas/orphans?lat=&lng=&radius=&cursor=&limit=` (radius in metres, 10 000 to 500 000, default 150 000; limit up to 50): `{features, next_cursor}`, the features as the atlas window gives them, each at its widened place, `properties.author` null, `properties.orphaned` true, `properties.widened_level` and `properties.precision_label` ("على مستوى الدولة" and the like). Near means: within the radius of the entry's public point, or the position lies inside the city, region or country the entry was widened to. Send the coarsened position the camera discovery sends (the 0.05° grid); the API snaps it again and keeps nothing. No block changes this list. Orphaned entries are not in `GET /atlas/entries` nor on place pages; once sponsored they are, at the same widened place, with `properties.sponsor`.
  - **An entry's id changes once**, when the daily job widens it (the old address answers 410). Never cache an id across that: take it from the list or the entry in hand.
  - `PUT /atlas/entries/{id}/sponsorship` (no body; «اكفل هذه البصيرة»): 200 `SponsorshipOut`; 404 for an entry the caller cannot see (a block against the sponsor); 409 `CONFLICT` for their own entry, a sponsored one or one that is not orphaned; 409 `UNDER_13_CANNOT_PUBLISH`; 409 `PUBLIC_IDENTITY_REQUIRED` and 403 for an unverified address. `DELETE` on the same path ends it (204; the reflection goes with it).
  - `PUT /atlas/entries/{id}/sponsorship/reflection` `{reflection}` (up to 500 characters): 200 `SponsorshipOut` with `reflection_status` `published` | `pending_review` | `rejected` | `removed` and `reflection_message` (Arabic, for the sponsor); 422 for words that read like Quran or hadith; 409 `UNDER_13_CANNOT_PUBLISH`.
  - `SponsorshipOut` now has `id` (the sponsorship's public id). `active` is always true and `ended_at` always null, since a sponsorship that ends is deleted (the fields stay so the client need not change).
  - `GET /atlas/entries/{id}` gains `orphaned`, `sponsor` (`{handle, public_name}`), `sponsor_reflection` (published only), `sponsor_reflection_id` (what `POST /reports` takes with `target_type` `sponsorship`) and `location.widened_level`; `author` and `post_id` are null for a widened entry. `GET /me/map-entries` shows status `orphaned`, `sponsor`, and `widened` (`{level, label, at}`); its `public.cell` is null once widened. `GET /me/sponsorships` lists the caller's current sponsorships on entries still on the atlas.
  - With `atlas_sponsorship` off the same entries come as plain widened ones: `orphaned` false, no sponsor fields, on the map and place pages.
  - The status `orphaned` has a label in `messages/ar.ts` (`publish.status.orphaned`); the screens may reword it.
- **Touches:** apps/web/src/{app/atlas,components/atlas,components/camera,messages}.
- **Done when:** The screens follow tajriba.md; nothing scores or ranks sponsors.
- **What was built:** `OrphansSection` («بصائر تنتظر من يكفلها») on the atlas, under the results, and in the camera discovery; it asks `GET /atlas/orphans` with the map's centre (set when the window is searched, never on every move) or the camera's centre, snapped by `coarsePoint` to the 0.05° grid inside `orphansNear`, so no caller can send a finer one, and never asks the device for its position. `SponsorPanel` on the entry page: «اكفل هذه البصيرة» for a verified member with a public identity (the missing step for a guest, an unverified account, a member with no identity), the sponsor line (a profile link while `social` is on, plain text otherwise), the sponsor's published reflection with «بلّغ عن هذا التأمل» (target `sponsorship`, signed-in members other than the sponsor), and for the sponsor «إنهاء الكفالة» behind a confirmation sheet and the reflection form (500 characters, status and the server's message, `removed` included, 422 scripture refusal). The three 409 `CONFLICT` refusals share one code, so the page reads the entry again and says which it was (own entry, already sponsored, not orphaned). A 410 on the entry page says the entry was withdrawn or its address changed when it was widened; no id is kept across that, every list reads again on display. «كفالاتي» is a third scope beside «بصائري المنشورة» (`MySponsorships`, current sponsorships only); the member's own list shows `orphaned`, the sponsor and the widening (level or label and day). Everything is hidden while `atlas_sponsorship` is off (the server pages pass it as a prop).

### 21.3 Reactions with a meaning

- **Status:** ✅ done 2026-10-05 09:22 (Tunis)
- **Goal:** Replace `post_likes` with `post_reactions` (post, member, kind `benefited` | `jazak`, time; one of each per member and post); move every existing like to `benefited` in the migration; feeds and posts answer both counts and the reader's own reactions; the «لك» feed ranks on them as it did on likes; the post screen shows «انتفعتُ بها» and «جزاك الله خيرًا» with their counts.
- **Depends on:** 16.1.
- **Touches:** apps/api/src/{models/social.py,services/post_service.py,services/feed_service.py,routers/posts.py}, a migration in the app chain, apps/web community components and messages, the generated web client, the terms if they name likes.
- **Done when:** No «like» or «أثر» is left in the API or the interface; account deletion removes a member's reactions.
- **Waiting on the owners:** an API contract change (AGENTS.md, ask first), approved by decision 61.
- **Notes:** Migration `20261005_160000` copies every like as `benefited`; `PUT`/`DELETE /posts/{id}/reactions/{kind}` replace the like routes; posts carry `reactions` counts and `viewer.reactions`; the «لك» feed treats either kind as met. The terms say «التفاعلات» and needed no change.

### 21.4 «أهدِ بصيرة»: giving an insight (plan only)

- **Status:** ⏸ waiting on the owners
- **Idea:** A member gives one of their insights to one member they follow or who follows them, with an optional short note (a few words, moderated). The receiver sees «أهداك فلان بصيرة» and may keep it in their own world. It is a gift of one insight, not a conversation: no reply, no thread, so decision 2's "no direct messages" holds. The interface leads with «هديّة» («تهادوا تحابوا» if shown, from the store by id) and may explain it as «صدقة علم».
- **Questions for the owners:**
  1. «أهدِ» or «تصدّق بها» as the action's name.
  2. Followers only, mutual follows only, or anyone not blocked.
  3. Does a kept gift count as learned in the receiver's world only after their own «تمّ»? (Suggested: yes.)
  4. A daily limit of gifts per member, against spam.
- **Touches when decided:** apps/api social models, services and routers, a migration, notifications, apps/web community and world, the terms and privacy text (a new data flow between members).
