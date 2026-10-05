# 07 · Personal world

**Phase:** 1 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-05 15:30 (Tunis)

Each completed insight lights a place in a fog-covered world, organised by the learning path. Hidden treasures are found along the way.

| Step                                        | Status | Notes                       |
| ------------------------------------------- | ------ | --------------------------- |
| World data: places, threads, treasures      | ✅     | Built; merges after review. |
| World screen with fog, places and treasures | ✅     | Replaced by 07.2.           |
| Reveals of the world picture (decision 59)  | ✅     | API, layout and repair.     |
| World picture screen (decision 59)          | ✅     | Web, tests, screenshots.    |

**How we check it**

- A new guest sees an inviting empty world; a completed insight opens a place.

## Tasks

### 07.1 World screen

- **Status:** ✅ 2026-10-04 16:09
- **Goal:** Fog world with places, threads and treasures.
- **Depends on:** 04.1
- **Touches:** apps/web world components and route.
- **Done when:** Empty state for a new guest works; related tests pass.

### 07.2 The world as one picture under clouds (decision 59)

- **Status:** ✅ 2026-10-05 15:30 — API (`world_reveals`, layout 1, the reveal at «تمّ», the repair of earlier completions, `POST /world/reveals/shown`) and the screen (canvas clouds, landmarks, HUD, panels, «بصائري», reveal effects), checked end to end in a browser.
- **Goal:** The owners' world kit: clouds over one landscape, a reveal per learned concept, «بصائري».
- **Depends on:** 07.1
- **Touches:** apps/api world models, services and routes; data/world/layout-1.json; apps/web world components and route.
- **Done when:** A newcomer sees clouds only; a completion lifts its concept's circle once, kept on the server and shown after a reload or on another device; repeats and races make one reveal; «بصائري» lists every learned insight; related tests pass.
