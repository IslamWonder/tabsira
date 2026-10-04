# 05 · Insight engine

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-04 18:31 (Tunis)

Finds the verse and hadith that truly fit the scene, checks them, and writes the explanation. It cites texts by reference only.

| Step                                             | Status | Notes                        |
| ------------------------------------------------ | ------ | ---------------------------- |
| Search by full text, concepts and meaning, fused | ✅     | Merged with 05.1.            |
| Re-ranking of the best candidates                | ✅     | Small model (nano), at once. |
| Evidence gate using editor rulings               | ✅     |                              |
| Explanation, «لماذا ظهر هذا؟», small step        | ✅     |                              |
| Evaluation on gold scenes (make eval)            | ✅     | 13/15 as expected, 0 leaks.  |
| Plug into the scan workflow and merge            | ✅     | 2026-10-04 17:51             |
| The twelve official cases                        | ✅     | 4 official, 8 derived.       |

**How we check it**

- make eval scores; scripture review; one real scan.

## Tasks

### 05.1 Insight engine: rebase, vectors schema, wiring, shared guards, review

- **Status:** ✅ 2026-10-04 17:51: merged. Scripture review passed with notes (demand counted twice per scan, the Quran word runs loaded once per process, short fragments of unshown hadiths below the 7-word store check, a lone weak text). Not run on the machine that merged it, whose network blocks the owners' bucket, the scripture sources and OpenAI: the archive import, `make eval` and a real scan on `https://tabsira.test`.
- **Goal:** Merge the insight engine and make it the scan workflow's real engine.
- **Steps, in order:**
  1. Rebase onto main. Main's app chain ends at `20261004_192500` (profile motion); resolve the conflicts with the scan workflow (models/scripture.py, models/**init**.py, tests/test_migrations.py, test_account_models.py, config, messages).
  2. Decision 48: move the retrieval tables (`quran_verse_embeddings`, `hadith_embeddings`, `embedding_runs`) to a new `vectors` schema with its own Alembic chain (`alembic_vectors`, initial revision on its own, keys to `app` with `ON DELETE CASCADE`), run last by `make migrate`; add `vectors` to the role's search path in `scripts/setup-db.sh` and the test database setup; drop the old app-chain retrieval migration (it was never on main).
  3. Point `scripts/vectors/import.sh` and `export.sh` at `vectors.*`, accept the extracted archive folder as an argument, and import the published archive (docs/EMBEDDINGS.md) into the development database instead of recomputing.
  4. Register the factory: `ENGINE_FACTORIES[ScanEngine.PIPELINE] = build_engine(settings, http, sessionmaker, client=...)` in `src/scans/engines.py`, and update the workflow's test that expects `unavailable_engine`.
  5. Switch every engine guard to the shared `guard_fold` and `repeats_store` (`src/scripture/guard_fold.py`, `overlap.py`): planner fields, verifier limits, explanation parts, steps, the clarification question; add an engine test where a modern-spelled 3:190 is refused.
  6. `make lint`, `uv run pytest -n 2` on retrieval, insight, scripture, scans, migrations, config; one `make eval`; scripture-guardian review; merge.
- **Depends on:** — (the scan workflow is on main).
- **Touches:** apps/api pipeline, retrieval, scans/engines.py, alembic (new vectors chain), scripts/setup-db.sh, scripts/migrate, scripts/vectors, docs/EMBEDDINGS.md, docs/BENCHMARK.md.
- **Done when:** a real scan on `https://tabsira.test` returns an engine insight with verse (and hadith when ruled), no leak, guards shared; review passes.

### 05.2 The twelve official test cases

- **Status:** ✅ 2026-10-04 17:42: 9 of 12 as expected on the first run, no scripture shown (docs/EVALUATION.md, «The twelve chat cases»)
- **Goal:** Add the challenge's twelve official cases (master prompt v2, sections 12 and 27) to `make eval`, with their expected outcomes.
- **Depends on:** 05.1
- **Touches:** apps/api/src/evaluation (chat cases and their report), src/cli/evaluate.py, apps/api/tests/evaluation/chat, scripts/eval.sh, docs/EVALUATION.md.
- **Done when:** `make eval` reports each case; results written in docs/EVALUATION.md.
- **Waiting on the owners:** the challenge package's own list of twelve. The spec quotes four (`official`); the other eight are ours (`derived`, from v2 §0, §10, §12, §14) and are replaced when the list arrives.

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

- **Status:** ✅ 2026-10-04 16:37: archive and every file inside verified from the public address
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
