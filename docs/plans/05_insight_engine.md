# 05 · Insight engine

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-06 09:28 (Tunis)

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
| Intents, hybrid search, verifier, pair (05.8)    | 🔄     | Code and tests; eval pending |

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
- **Cases:** the four the spec quotes (`official`) and eight of our own from the spec (`derived`: v2 §0, §10, §12, §14). We follow our own spec; the challenge package's list is not awaited.

### 05.3 Insight quality tuning

- **Status:** ✅ 2026-10-04 18:48: scan p50 26.7 s → about 18 s, p95 42.8 s → about 22 s; general reminders 9 of 32 → 2 to 5 of 16; chat cases 9 → 11 of 12 (docs/EVALUATION.md, «Runs of task 05.3»)
- **Goal:** Better scene-to-text fit: abstain on empty scenes (the still phone), fewer thematic reminders, no loose verses (the market drew the ablution verse), more of the hoped-for texts. Tune the planner prompt and the gold expectations.
- **Depends on:** 05.1
- **Touches:** apps/api pipeline (verifier, composer, engine ranking, sensitivity), scans/workflow.py, the chat prompt, apps/api/tests/evaluation, docs/EVALUATION.md, decision 50.
- **Done when:** `make eval` improves on every measure above with no leak; scripture review passes.
- **Not reached, for the owners:** about 12 s needs one call fewer (05.7); the still phone does not abstain (its photo shows a notebook and a pen; the spec asks only that the phone never trigger the news lesson, which holds: keep the gold's «abstain» or change it to «a reminder at most»?); the hoped-for texts stay at 1 to 3 of 9, with equally fitting verses chosen; the wine scene needs an alcohol entity in the ontology; the app's own referral line «اسأل أهل العلم…» is a masculine imperative (messages catalogue). The rebased branch was not run end to end (its tests pass).

### 05.4 Import the vector archive in setup and deploy

- **Status:** ✅ 2026-10-04 19:22: `make data` imports the archive on laptops and on the production host (`scripts/vectors/ensure.sh`); run on the development database here
- **Goal:** A fresh development machine or production server imports `tabsira-vectors-<date>.tar.gz` (docs/EMBEDDINGS.md) instead of computing vectors: `make data` imports it when `VECTORS_ARCHIVE` points at a local copy, else downloads it from the bucket (`VECTORS_ARCHIVE_URL`), checks its `.sha256`, and runs `scripts/vectors/import.sh`, before `embed_corpus` fills the gaps.
- **Depends on:** 05.1 (the retrieval tables).
- **Touches:** scripts/data.sh, scripts/vectors/ensure.sh, the typed settings and .env.example (`VECTORS_ARCHIVE`, `VECTORS_ARCHIVE_URL`), deploy/env.production.example, docs/OPERATIONS.md, docs/EMBEDDINGS.md, docs/SETUP.md.
- **Done when:** On an empty database, `make data` imports 165,072 vectors and `embed_corpus` then reports nothing to send; no key or archive is committed.

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

### 05.7 Judge and write in one call per candidate

- **Status:** ⬜ open
- **Goal:** Bring a scan to about 12 s at p50: the verifier and the composer become one call per candidate that judges the shortlisted texts and writes the explanation of the one it would keep; the gate still decides (rulings, texts already seen), and a different pick than the model's is written again by the composer.
- **Depends on:** 05.3
- **Touches:** apps/api/src/pipeline/insight (evidence, composer, a new prompt), tests/insight, docs/EVALUATION.md.
- **Done when:** `make eval` shows p50 near 12 s with no leak and no loss on the measures of 05.3; scripture review passes.

### 05.8 Rebuild the search path on the owners' brief of 2026-10-05

- **Status:** 🔄 2026-10-05 10:55: code, tests and docs done on `main` (local commits); `make eval` not run, this machine has no provider key. Pre-existing failures left alone: `tests/scans/test_account_flow.py::test_the_export_holds_everything_the_learner_saved_and_never_a_photo` and `tests/scans/test_insights.py::test_an_insight_shows_its_verse_exactly_as_stored_and_waits_for_its_hadith_ruling` fail on the untouched main too (the world reveals and the chat `closed` field).
- **Goal:** Meanings are hypotheses before the search and insights are written after the evidence: a `SemanticIntentPlanner` (no learner, no learning units, keyword and sentence queries per corpus), hybrid search with one RRF weight per channel (50 per list, 120 fused, 30 reranked, 12 verified), an `EvidenceRelevanceVerifier` that accepts or rejects every text with its relation, word positions, link, needed context, assumptions and reject reason and names the pair, a gate that completes a pair only within the same relation tier, a composer that writes from the confirmed intent, honest statuses (`incomplete_evidence_pair`, `corpus_unavailable`, `retrieval_error`), a per-scan trace in `scans.engine_trace`, and no example scene, query, insight or scripture in any production prompt.
- **What was proven broken before (read from the code, 2026-10-05):** the planner decided the title, value and concept before any search and received the learner's profile; its short concept phrases fed every channel, so the vector channel embedded keyword lists; the reranker read every query of a candidate glued with «،» and only the first 8 fused texts, and the verifier only 4 per corpus of 30 fused; the learning unit's anchor texts joined the fusion as a list, a fixed map from scene to text; a verse and a hadith were picked independently from the top tier; a verifier «weak» became a `thematic_reminder` shown as an insight; a failed query embedding silently became a lexical-only answer; nothing recorded why a text was kept or dropped.
- **Measured offline on the real corpus (no key needed):** lexical and concept channels alone, rain intent: hadith list #1 Bukhari 1032 (the rain example), Quran list holds 2:164 at #5; book intent: Tirmidhi 2654 and Abu Dawud 3641 in the first three hadiths; the channel of every candidate is visible in the trace.
- **Scripture review (2026-10-05):** the first pass failed on two high findings, both fixed before commit: the server completed a pair with a text from another relation tier, and an unruled hadith was replaced by a same-tier one against decisions 18 and 58 (now: the verse alone and the hadith queued; a hadith an editor ruled out may be replaced in its tier only). Also fixed: the displayed «وجه الصلة» link now meets the acceptance re-check, intents are named by the server (the model writes no id into the trace), a verifier that keeps leaking ends the scan as `model_unavailable`, grade words in a verifier field are dropped by the server, and the privacy text names the search record. Left for the owners: the limits of a hadith ruled out after the scan stay in «لماذا ظهر هذا؟» (low).
- **Decision 65 (2026-10-05, later the same day):** a hadith with no ruling is shown as stored and no ruling is displayed anywhere; the gate no longer queues or waits (`incomplete_evidence_pair` is reserved, never produced), a hadith an editor ruled out is still left out, and the composer and chat prompts gained a version that says the app shows no grade.
- **§7 and §12 of the brief, read again with the owners (2026-10-05, later):** the hadith candidate source is the enriched Sunnah file (3,920 sahih records), not the whole store: with `HADITH_SEARCH_SCOPE=enriched_first` the hadith lists are narrowed to the narrations the records match in the nine books, one narration per record, the whole store is searched only when no record fits an intent (one more verifier call), and a verse reaches the verifier with its neighbouring verses as context. The field contract of the two files is in docs/CORPUS_FILES.md.
- **Not done, for the owners:** `make eval` before and after on a machine with the key (the comparison the brief asks for); the reranker setting (`RERANKER=llm` now reads the right input, decision 50 keeps it off until measured); fetching dorar.net tafseer, dawa.center or islamic-content.com for the explanation (master prompt v2 §28 defers it and AGENTS forbids a new third-party call without asking); chunking long hadiths; a cache for retrieval (none exists: every scan searches the store).
- **Depends on:** 05.3.
- **Touches:** apps/api pipeline/insight (intents, search, evidence, composer, engine, learning), retrieval (fusion weights, reranker wording, vector check), prompts (four new versions), scans/workflow, models/scan + migration `20261005_110000`, services/chat_retrieval, schemas/insight (`link`), errors; apps/web scan messages, scan screen, why-sheet, generated API types; docs/plans/20_prompts.md.
- **Done when:** `make eval` on the rebuilt path shows no leak, every reference resolved, and the per-scene choices read as fitting by a human; the scripture review passes.

### 05.10 «وجه الصلة» says what the text says, or nothing

- **Status:** ⏸ optional; the owners kept the line on 2026-10-06
- **Goal:** a quality improvement, not a contest requirement: the line is part of the generated explanation, which is labelled as AI-assisted (`docs/spec/contest-reference.md`). The «وجه الصلة» line of «لماذا ظهر هذا؟» shows `matched_on`, the search query that ranked the text (`pipeline/insight/search.py` `_matched_on`), and the audit of 2026-10-06 found lines that describe the photo or a hoped-for topic instead of the text (a cat in a hadith about a dog). Either the sheet shows only the verifier's checked «وجه الارتباط», or `matched_on` is labelled as what was searched for, never as what the text says.
- **Touches:** apps/web components/insight/why-sheet.tsx and messages/scan.ts; nothing in the API (the field stays for the trace).
- **Reviews:** scripture review (what is shown about a text).

### 05.11 No hadith without an approved ruling

- **Status:** ✅ closed 2026-10-06, owners' decision: the current behaviour (decision 65) stays unchanged; nothing to build
- **Goal:** the contest's reference pack asks that no hadith be attributed without a source and an approved ruling: the two Sahihs, or a hadith whose soundness was checked (dorar.net/hadith, shamela.ws). Decision 65 shows a hadith with no ruling yet, `app.hadith_rulings` is empty, and the mock audit found three hadiths that every grader in the corpus calls weak shown as evidence (tirmidhi:3127, ibnmajah:1819, abudawud:3402). At least: never show a hadith that the corpus graders call weak; then decide whether an unruled hadith outside the two Sahihs may show at all.
- **Touches:** apps/api pipeline/insight evidence gate and services/content (`shown_evidence`), tests; DECISIONS.md once the owners decide.
- **Reviews:** scripture review.
