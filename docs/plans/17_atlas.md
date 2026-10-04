# 17 · World atlas «أطلس بصائر العالم»

**Phase:** 2 · **Priority:** Medium · **Status:** ✅ · **Updated:** 2026-10-04 19:43 (Tunis)

A real map of shared insights, at approximate locations only.

| Step                                     | Status | Notes                                                                                                 |
| ---------------------------------------- | ------ | ----------------------------------------------------------------------------------------------------- |
| Place search and the approximation grid  | ✅     |                                                                                                       |
| Map entries: publish and withdraw        | ✅     | Task 17.1: two tables, the exact point private, the cell centre public.                               |
| Map screen with clusters and place pages | ✅     | Task 17.1: MapLibre with OpenFreeMap tiles, filters, place pages, placing an insight.                 |
| Map entries in the moderation queue      | ✅     | Task 17.2: held and reported entries, approve or remove, public place only.                           |
| Privacy re-review fixes before switch-on | ✅     | Task 17.3: reports and the handle with the atlas alone, no caching, day precision, tombstones, terms. |

**How we check it**

- Exact locations never reach a public page (tested).
- The admin queue shows a map entry's public place and cell only; the capture point is never read (tested).

## Tasks

### 17.1 Map entries and the atlas map

- **Status:** ✅ 2026-10-04 17:20, owners' Wave 4 agent (branch task/17.1-atlas, based on task/16.1-social-screens)
- **Goal:** Publish and withdraw places at approximate locations; MapLibre map with clusters.
- **Depends on:** Phase 2.
- **Touches:** apps/api map entries, apps/web atlas.
- **Done when:** Exact points never public.
- **Reviews:** privacy and scripture reviews applied (public answers carry a day, never a time, and no insight id; blocks apply; an account under 13 places nothing; the posts' evidence and leak checks run when placing and publishing; a withdrawn entry keeps no label and a re-placed one takes a new address; enough reports hide an entry until a moderator decides).
- **Left for the owners:** `FEATURE_ATLAS` stays off in production until tasks 17.2 and 17.3 land; the terms' promise of coarsening a location and publishing an exact point by choice was removed by task 17.3 (approximate only, as AGENTS.md requires).

### 17.2 Map entries in the moderation queue

- **Status:** ✅ 2026-10-04 19:34, owners' agent (branch task/17.2-map-entries-moderation)
- **Goal:** The admin moderation queue lists held and reported map entries (`ReportTarget.MAP_ENTRY`, `MapEntryStatus.PENDING_REVIEW`) and lets a moderator approve or remove them; `moderation_service.approve` and `remove` already accept a map entry.
- **Depends on:** 17.1
- **Touches:** apps/api/src/admin/views/moderation.py and its templates, tests/test_admin_moderation.py.
- **Done when:** A reported entry can be taken down from the admin area; then the owners may switch `FEATURE_ATLAS` on in production.
- **Reviews:** privacy review of the diff applied: the admin reads `map_entries` only, never `map_capture_points`; the pages show the GeoNames label, the cell size and the cell centre the public API already serves, and no photo; a draft entry has no page; the exact point is asserted absent from every page in the tests.
- **Left for the owners:** `FEATURE_ATLAS` is still off in `deploy/env.production.example`; switching it on is the owners' call.

### 17.3 Atlas switch-on fixes

- **Status:** ✅ 2026-10-04 19:43, owners' agent (branch task/17.3-atlas-switch-on-fixes)
- **Goal:** Apply findings 2 to 7 of the privacy re-review (`../tabsira-artifact/reviews/privacy-re-review-social-atlas-2026-10-04.md`): `POST /reports` takes a map-entry report and `/me/public-identity` lets a member choose the handle `PublicMember` needs while only `FEATURE_ATLAS` is on (nothing else of the network opens, and a target whose feature is off is 404); every `/atlas` answer is `no-store`; the place-page cursor and the sitemap `lastmod` carry the day of publication, never the hour; re-placing a published entry keeps the record that it was public, so a later withdrawal still answers 410; `PUT`/`DELETE /blocks/{handle}` answer 204 for a handle nobody holds, as for a member who blocked the caller; the terms say the atlas publishes approximate cells only, that no exact point can be published, and name the report targets the code has.
- **Depends on:** 17.1
- **Touches:** apps/api/src/{deps.py,routers/reports.py,routers/members.py,services/report_service.py,services/atlas_service.py,services/atlas_sitemap.py,middleware/no_store.py}, their tests, apps/web/src/messages/legal.ts, the generated web client.
- **Done when:** The six findings are closed with their tests; 17.2 being merged, the owners may switch `FEATURE_ATLAS` on in production (`deploy/env.production.example` keeps it off).
