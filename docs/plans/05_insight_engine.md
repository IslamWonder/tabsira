# 05 · Insight engine

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-04 16:27 (Tunis)

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

### 05.4 Import the vector archive in setup and deploy

- **Status:** ⬜ open, after 05.1
- **Goal:** A fresh development machine or production server imports `tabsira-vectors-<date>.tar.gz` (docs/EMBEDDINGS.md) instead of computing vectors: `make data` imports it when `VECTORS_ARCHIVE` points at a local copy, before `embed_corpus` fills the gaps; the production provisioning and docs/OPERATIONS.md download it from the bucket (`vectors/` in the owners' S3), check its `.sha256`, and run its `import.sh`.
- **Depends on:** 05.1 (the retrieval tables).
- **Touches:** scripts/data.sh, scripts/vectors/, the typed settings and .env.example (`VECTORS_ARCHIVE`), deploy/provision-app.sh or a deploy step, docs/OPERATIONS.md, docs/EMBEDDINGS.md.
- **Done when:** On an empty database, `make data` with `VECTORS_ARCHIVE` set imports 165,072 vectors and `embed_corpus` then reports nothing to send; no key or archive is committed.

### 05.5 Verify the uploaded archive

- **Status:** ⬜ open, ready once the owners' upload finishes (needs read access to the bucket)
- **Goal:** Download `vectors/tabsira-vectors-2026-10-04.tar.gz` and its `.sha256` from the owners' bucket, check the SHA-256 is `aca79a6d46eee5bed8d6b2a16c726f279c3af5a52651b3fc1ba362aac7c052d4`, extract it, and run `sha256sum -c SHA256SUMS` inside.
- **Depends on:** the owners' upload.
- **Touches:** nothing in the repository; record the result in docs/EMBEDDINGS.md ("Current archive") in one line.
- **Done when:** Both checks pass and the line says when it was verified, or the owners are told what differs.

### 05.6 Export a new vector archive when the texts or models change

- **Status:** ⬜ when needed
- **Goal:** After a change to the store, its annotations or the embedding models, compute what changed with `embed_corpus`, run `scripts/vectors/export.sh`, upload the archive and its `.sha256` to `vectors/`, verify it as in 05.5, and update docs/EMBEDDINGS.md.
- **Depends on:** 05.1
- **Touches:** docs/EMBEDDINGS.md only; the archive goes to the bucket, never to git.
- **Done when:** The new archive is verified and documented; the previous one is kept until then.
