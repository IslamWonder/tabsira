# 17 · World atlas «أطلس بصائر العالم»

**Phase:** 2 · **Priority:** Medium · **Status:** 🔄 · **Updated:** 2026-10-04 20:45 (Tunis)

A real map of shared insights, at approximate locations only.

| Step                                     | Status | Notes                                                                                                                                      |
| ---------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Place search and the approximation grid  | ✅     |                                                                                                                                            |
| Map entries: publish and withdraw        | ✅     | Task 17.1: two tables, the exact point private, the cell centre public.                                                                    |
| Map screen with clusters and place pages | ✅     | Task 17.1: MapLibre with OpenFreeMap tiles, filters, place pages, placing an insight.                                                      |
| Map entries in the moderation queue      | ✅     | Task 17.2: held and reported entries, approve or remove, public place only.                                                                |
| Privacy re-review fixes before switch-on | ✅     | Task 17.3: reports and the handle with the atlas alone, no caching, day precision, tombstones, terms.                                      |
| Wave 4 audit web fixes                   | ✅     | Task 17.4: 404 while off, camera wording, the view in the address, concept and own-entries filters, publish actions inside sharing, terms. |
| «نفس المعنى حول العالم» and more filters | ⏸      | Task 17.5: `GET /map/related`, concept labels, scene type and «جديد عليّ».                                                                 |
| EXIF location as a placing candidate     | ⏸      | Task 17.6: the upload's own GPS offered on the placing screen, never the device's position by default.                                     |

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

### 17.4 Wave 4 audit web fixes

- **Status:** ✅ 2026-10-04 20:45, owners' agent (branch task/17.4-atlas-web-fixes)
- **Goal:** Close the web gaps of the wave 4 compliance audit (`../tabsira-artifact/reviews/audit-wave4-extension-2026-10-04.md`).
- **Depends on:** 17.3, 18.1, 04.11.
- **Touches:** apps/web/src/{app/atlas,app/community,app/insight,components/atlas,components/insight/share-sheet.tsx,components/insight/insight-screen.tsx,config/server-env.ts,atlas/view-state.ts,messages}, .env.example, deploy/env.production.example, apps/api/src/config.py and the API tests naming the legal version, docs/PRIVACY.md, docs/plans/18.
- **What was done:** `/atlas`, `/atlas/publish`, `/community` and `/community/publish` answer 404 while `FEATURE_ATLAS` or `FEATURE_SOCIAL` is off, read on every request as the camera page does (decision 1). The camera's chip says «في اتجاه الكاميرا», never that a place is in view (extension §6B, §13.15). «اعرض على الخريطة» from the camera opens the atlas on the same centre and radius with the nearest entry selected; the view, selection and filters live in the address's fragment, which never reaches a server, so coming back restores them (§4). The atlas filters gained «بصائري المنشورة» (the owner's entries from `GET /me/map-entries`, every state, each leading to its page or back to the placing screen) and the concept filter the API already accepts, reached from an entry's «بصائر بالمعنى نفسه على الخريطة»; the API gives concept ids without names, so there is no picker yet (17.5). The share sheet offers «انشر على الخريطة» and «انشر في تواصل» (§2.3–2.4), each only while its feature is on and only where sharing itself is offered, leading to the existing publish screens with `?insight=`. The terms and privacy say an account under 13 cannot place an insight on the atlas and that the camera's video and sensor readings stay on the device; the legal version is `2026-10-04T20:00Z` (decision 35), in the web, the API default, `.env.example` and the production template.
- **Left for the owners:** the version label is a time on the same day as the first version; a plain second day would have been a lie today. Scene type and «جديد عليّ» need data the API does not provide (17.5).

### 17.5 «نفس المعنى حول العالم» and the remaining filters

- **Status:** ⏸ open
- **Goal:** Extension §8b and §12: `GET /map/related` returns the published entries sharing an insight's `entity_ids`, for the entry page's «نفس المعنى حول العالم»; the API names concepts (an id with its Arabic label, from the ontology) in the atlas answers so the web can offer a concept picker instead of the id-only filter of 17.4; the scene type and «جديد عليّ» filters of §4 (what the signed-in viewer has not opened yet) once the API carries a scene type per entry and a viewer-side "seen" signal.
- **Depends on:** 17.4.
- **Touches:** apps/api/src/{routers/atlas.py,services/atlas_service.py,schemas/atlas.py} and their tests, the generated web client, apps/web/src/{atlas,components/atlas}.
- **Done when:** An entry page lists related entries by shared meaning; the atlas filters by a named concept, by scene type and by «جديد عليّ»; no public answer carries an insight id or a time (17.1's tests still pass).

### 17.6 EXIF location of an upload as a placing candidate

- **Status:** ⏸ open
- **Goal:** Extension §3 «صورة مرفوعة من المعرض»: `image_service.read_capture_metadata` already reads the GPS position, accuracy and time of an uploaded file (`CaptureMetadata`, source `photo_exif`) before stripping, but nothing consumes it. Keep it for the owner alone, bound to the scan, and offer it on the placing screen as a candidate («أين التُقطت الصورة؟») beside a place found by name and a tap on the map; never assign the device's current position to an old photo by default, never call EXIF «GPS مؤكد», and record `location_source = photo_exif` when the owner confirms it.
- **Depends on:** 17.1; the photo flow of the API audit (a kept photo must not keep its EXIF).
- **Touches:** apps/api/src/{pipeline,scans,services/atlas_service.py,models}, a migration or a private field on the scan, the owner's `GET /insights/{id}/map`, apps/web/src/components/atlas/map-publish-screen.tsx and tests.
- **Done when:** Acceptance tests 2 and 4 of extension §13 pass: an old photo with EXIF is never placed where it was uploaded; a photo without EXIF accepts a manual place or stays off the map; the EXIF point never reaches a public answer.
