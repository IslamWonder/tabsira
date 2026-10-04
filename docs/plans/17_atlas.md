# 17 · World atlas «أطلس بصائر العالم»

**Phase:** 2 · **Priority:** Medium · **Status:** 🔄 · **Updated:** 2026-10-04 17:48 (Tunis)

A real map of shared insights, at approximate locations only.

| Step                                     | Status | Notes                                                                                 |
| ---------------------------------------- | ------ | ------------------------------------------------------------------------------------- |
| Place search and the approximation grid  | ✅     |                                                                                       |
| Map entries: publish and withdraw        | ✅     | Task 17.1: two tables, the exact point private, the cell centre public.               |
| Map screen with clusters and place pages | ✅     | Task 17.1: MapLibre with OpenFreeMap tiles, filters, place pages, placing an insight. |

**How we check it**

- Exact locations never reach a public page (tested).

## Tasks

### 17.1 Map entries and the atlas map

- **Status:** ✅ 2026-10-04 17:20, owners' Wave 4 agent (branch task/17.1-atlas, based on task/16.1-social-screens)
- **Goal:** Publish and withdraw places at approximate locations; MapLibre map with clusters.
- **Depends on:** Phase 2.
- **Touches:** apps/api map entries, apps/web atlas.
- **Done when:** Exact points never public.
- **Reviews:** privacy and scripture reviews applied (public answers carry a day, never a time, and no insight id; blocks apply; an account under 13 places nothing; the posts' evidence and leak checks run when placing and publishing; a withdrawn entry keeps no label and a re-placed one takes a new address; enough reports hide an entry until a moderator decides).
- **Left for the owners:** `FEATURE_ATLAS` stays off in production until task 17.2 lands; the terms promise coarsening a location and publishing an exact point by choice, which the code does not offer (approximate only, as AGENTS.md requires).

### 17.2 Map entries in the moderation queue

- **Status:** ⬜ open
- **Goal:** The admin moderation queue lists held and reported map entries (`ReportTarget.MAP_ENTRY`, `MapEntryStatus.PENDING_REVIEW`) and lets a moderator approve or remove them; `moderation_service.approve` and `remove` already accept a map entry.
- **Depends on:** 17.1
- **Touches:** apps/api/src/admin/views/moderation.py and its templates, tests/test_admin_moderation.py.
- **Done when:** A reported entry can be taken down from the admin area; then the owners may switch `FEATURE_ATLAS` on in production.
