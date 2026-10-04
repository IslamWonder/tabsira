# 05 · Insight engine

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-04 14:51 (Tunis)

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

- **Status:** 🔄 main machine
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
