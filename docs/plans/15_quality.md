# 15 · Quality gates

**Phase:** 1 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-04 15:13 (Tunis)

Every change is tested; nothing merges below 100 % coverage.

| Step                                                | Status | Notes            |
| --------------------------------------------------- | ------ | ---------------- |
| 100 % coverage, lint and type checks on every merge | ✅     |                  |
| Code summary command (make stats)                   | ✅     |                  |
| Gold scenes evaluation (make eval)                  | 🔄     | With the engine. |
| HTTP smoke test (make smoke)                        | ✅     | 2026-10-04 15:13 |

**How we check it**

- make lint, make coverage, make smoke.

## Tasks

### 15.1 HTTP smoke test

- **Status:** ✅ 2026-10-04 15:13
- **Goal:** `make smoke` checks the main pages and API routes of a running app, locally and against tabsira.me.
- **Depends on:** 04.1
- **Touches:** scripts/smoke (new), Makefile.
- **Done when:** Passes on tabsira.test; fails clearly when a route breaks.

### 15.2 Rewrite old commits without other projects' names

- **Status:** ⬜ main machine, end of phase
- **Goal:** Remove every mention from history once all branches merged.
- **Depends on:** All phase 1 branches merged.
- **Touches:** Git history only.
- **Done when:** No mention in any commit; owners push once.
