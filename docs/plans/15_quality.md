# 15 · Quality gates

**Phase:** 1 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-04 14:36 (Tunis)

Every change is tested; nothing merges below 100 % coverage.

| Step                                                | Status | Notes            |
| --------------------------------------------------- | ------ | ---------------- |
| 100 % coverage, lint and type checks on every merge | ✅     |                  |
| Code summary command (make stats)                   | ✅     |                  |
| Gold scenes evaluation (make eval)                  | 🔄     | With the engine. |
| HTTP smoke test (make smoke)                        | ⬜     |                  |

**How we check it**

- make lint, make coverage, make smoke.
