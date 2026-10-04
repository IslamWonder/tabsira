# 05 · Insight engine

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-04 16:09 (Tunis)

Finds the verse and hadith that truly fit the scene, checks them, and writes the explanation. It cites texts by reference only.

| Step                                             | Status | Notes                       |
| ------------------------------------------------ | ------ | --------------------------- |
| Search by full text, concepts and meaning, fused | ✅     | Built; merges after review. |
| Re-ranking of the best candidates                | ✅     | Measured before choosing.   |
| Evidence gate using editor rulings               | ✅     |                             |
| Explanation, «لماذا ظهر هذا؟», small step        | ✅     |                             |
| Evaluation on gold scenes (make eval)            | ✅     |                             |
| Plug into the scan workflow and merge            | 🔄     |                             |
| The twelve official cases                        | ⬜     |                             |

**How we check it**

- make eval scores; scripture review; one real scan.

## Tasks

### 05.1 Insight engine: merge and plug into the scans

- **Status:** 🔄 branch task/05.1-insight-engine: rebase, re-chain, wire, shared guards, review, merge (see its brief)
- **Goal:** Merge the engine and register it as the scan workflow's real engine.
- **Depends on:** 04.1
- **Touches:** apps/api pipeline, retrieval, vision /rerank.
- **Done when:** make eval scores recorded; scripture review; one real scan.

### 05.2 The twelve official test cases

- **Status:** ⬜ open
- **Goal:** Add the challenge's twelve official cases (master prompt v2, sections 12 and 27) to `make eval`, with their expected outcomes.
- **Depends on:** 05.1
- **Touches:** apps/api/tests/evaluation (data and scoring), docs/BENCHMARK.md.
- **Done when:** `make eval` reports each case; results written in docs/BENCHMARK.md.

### 05.3 Insight quality tuning

- **Status:** ⬜ open
- **Goal:** Better scene-to-text fit: abstain on empty scenes (the still phone), fewer thematic reminders, no loose verses (the market drew the ablution verse), more of the hoped-for texts (3 of 9 today). Tune the planner prompt and the gold expectations.
- **Depends on:** 05.1
- **Touches:** apps/api pipeline prompts and planner, apps/api/tests/evaluation, docs/EVALUATION.md.
- **Done when:** `make eval` improves on every measure above with no leak; scripture review passes.
