# 20 · Prompts and search: where they live

A map of every model prompt in the code, and of how search finds the texts behind an insight, so the owners can review and change them in one place. Read-only inventory: it describes the code, it does not replace it. Keep it in step whenever a prompt file or a prompt constant changes.

**Phase:** 1 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-05 07:56 (Tunis)

## How prompts work

- A prompt is a text file `apps/api/src/pipeline/prompts/<name>.v<N>.txt`, loaded by `load_prompt()` in [prompt.py](../../apps/api/src/pipeline/prompt.py).
- **Changing what a prompt says means a new file with the next version** (`...v6.txt`), then pointing the `SYSTEM_PROMPT` / `USER_PROMPT` constant at it. Old versions stay in the folder as history. A result records `name@sha256`, so every answer names the exact text that produced it.
- Some prompts take values (`render(...)`, `string.Template`). The model never writes scripture: its output carries evidence ids only (AGENTS.md, Never).
- Prompts are English instructions for the model; user-visible text is Arabic and lives in the web messages modules, not here.

## Versioned prompt files (current version in bold)

| Stage                     | File in `apps/api/src/pipeline/prompts/`       | Selected by                                                                                 | Used in                                                                                           |
| ------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Scene analysis, system    | `scene_analyzer_system.`**`v1`**               | `SYSTEM_PROMPT` in [scene_analyzer.py:56](../../apps/api/src/pipeline/scene_analyzer.py:56) | [scene_analyzer.py:140](../../apps/api/src/pipeline/scene_analyzer.py:140)                        |
| Scene analysis, user      | `scene_analyzer_user.`**`v1`**                 | `USER_PROMPT` in [scene_analyzer.py:57](../../apps/api/src/pipeline/scene_analyzer.py:57)   | [scene_analyzer.py:141](../../apps/api/src/pipeline/scene_analyzer.py:141)                        |
| Insight planner, system   | `insight_planner_system.`**`v1`**              | `SYSTEM_PROMPT` in [planner.py:39](../../apps/api/src/pipeline/insight/planner.py:39)       | [planner.py:289](../../apps/api/src/pipeline/insight/planner.py:289), `max_insights` rendered in  |
| Evidence verifier, system | `insight_verifier_system.`**`v1`**             | `SYSTEM_PROMPT` in [evidence.py:53](../../apps/api/src/pipeline/insight/evidence.py:53)     | [evidence.py:192](../../apps/api/src/pipeline/insight/evidence.py:192)                            |
| Insight composer, system  | `insight_composer_system.`**`v2`** (v1 kept)   | `SYSTEM_PROMPT` in [composer.py:51](../../apps/api/src/pipeline/insight/composer.py:51)     | [composer.py:269](../../apps/api/src/pipeline/insight/composer.py:269)                            |
| Insight chat, system      | `insight_chat_system.`**`v5`** (v2 to v4 kept) | `SYSTEM_PROMPT` in [chat_service.py:61](../../apps/api/src/services/chat_service.py:61)     | [chat_service.py:294](../../apps/api/src/services/chat_service.py:294), `shown_texts` rendered in |
| Insight chat, user        | `insight_chat_user.`**`v2`**                   | `USER_PROMPT` in [chat_service.py:62](../../apps/api/src/services/chat_service.py:62)       | [chat_service.py:277](../../apps/api/src/services/chat_service.py:277)                            |

## Prompt text built in code (not versioned files)

| What                                    | Where                                                                                          | Note                                                                                                                             |
| --------------------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Rerank instruction, `LLM_RERANK_SYSTEM` | [retrieval/reranker.py:135](../../apps/api/src/retrieval/reranker.py:135)                      | Inline string; numbers and scores only, never text (the `gpt-5.4-nano` rerank). Not versioned, so a change leaves no hash trail. |
| Planner user message                    | `user_message()` in [planner.py:210](../../apps/api/src/pipeline/insight/planner.py:210)       | Assembles the scene for the planner.                                                                                             |
| Verifier user message                   | `verifier_message()` in [evidence.py:135](../../apps/api/src/pipeline/insight/evidence.py:135) | Assembles scene and shortlists.                                                                                                  |
| Composer user message                   | `composer_message()` in [composer.py:105](../../apps/api/src/pipeline/insight/composer.py:105) | Assembles scene, one result, learner context.                                                                                    |
| Chat evaluation                         | [evaluation/chat_eval.py:214](../../apps/api/src/evaluation/chat_eval.py:214)                  | Passes the chat system prompt under `prompt_version="evaluation"`.                                                               |

The vision service has no prompt: its reranker module only mentions the master prompt in a docstring.

## Where a prompt is checked

- [tests/test_prompt.py](../../apps/api/tests/test_prompt.py) covers loading and hashing.
- `make eval` (gold scenes, chat cases) is how a new version is compared with the last; results go in [docs/EVALUATION.md](../EVALUATION.md) (chat: v2 scored 9/12, v3 11/12).

## Changing a prompt

1. Copy the current file to the next version, edit the copy.
2. Point the constant at it; keep the old file.
3. Run the tests of the area (`uv run pytest -n 1 tests/<area>`) and `make eval`; note the scores in `docs/EVALUATION.md`.
4. Anything that touches what is shown as Quran or hadith, or the leak guards, gets the scripture-guardian review before commit.
5. Update this file in the same commit.

## How search works: from a scene to the texts behind an insight

Orchestrated by `PipelineInsightEngine` in [pipeline/insight/engine.py](../../apps/api/src/pipeline/insight/engine.py). Nothing a search returns is ever displayed as found: a result is ids, scores and the query that found them. Scripture is loaded from the store by id afterwards (AGENTS.md, Never).

### The flow

```
scene (from the scene analyzer)
  1. UNDERSTAND  ontology + learning path  ->  planner (LLM)  ->  up to 3 candidates,
                                                each with Quran queries and hadith queries
  2. SEARCH      per candidate, per corpus (Quran and hadith apart):
                   embed queries (one call) -> 3 searches per query + path anchors
                   -> RRF fusion -> top 30 -> rerank the head (8) -> keep 4
  3. VERIFY      verifier (LLM) judges the 4+4 texts of each candidate; the gate keeps the eligible
                 and relevant ones. Nothing passed: planner retries (2 rounds at most)
  4. COMPOSE     composer (LLM) writes the explanation; the leak guard rejects scripture-like text
```

### Step by step, with the code

| #   | What happens                                                                                                                                                                                                                                                                                                                | Where                                                                                                                                      | Knobs (constant or setting)                                                                                                                                              |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | The planner turns the scene into candidates: a concept, a relation type and concept queries in today's Arabic («الرحمة بالحيوان»), separate lists for the Quran and the hadith. A corpus with no queries is not searched.                                                                                                   | [planner.py](../../apps/api/src/pipeline/insight/planner.py), prompt `insight_planner_system.v1`                                           | `max_insights` (3), `planner_model`                                                                                                                                      |
| 2   | Learning-path units that fit the scene are offered to the planner; a chosen unit's anchors (`Q:30:50`, `H:bukhari:1032`) join the search as a hint list. A key that names nothing stored resolves to nothing.                                                                                                               | [learning.py](../../apps/api/src/pipeline/insight/learning.py), [refs.py](../../apps/api/src/retrieval/refs.py), `_anchors()` in engine.py | `UNIT_OPTIONS` (8)                                                                                                                                                       |
| 3   | All queries of a round are embedded in one call. If it fails, the search goes on without vectors and logs it.                                                                                                                                                                                                               | `embed_queries()` in [search.py](../../apps/api/src/pipeline/insight/search.py)                                                            | `embedding_model`, `embedding_dimensions` per provider in [config.py](../../apps/api/src/config.py)                                                                      |
| 4   | **Three searches per query**, each returns up to 30 hits (id and score).                                                                                                                                                                                                                                                    | `EvidenceSearch.search()`                                                                                                                  | `SEARCH_TOP` (30)                                                                                                                                                        |
| 4a  | **Vector:** cosine distance to the stored document vectors of the same model and size, on an HNSW index.                                                                                                                                                                                                                    | [vector.py](../../apps/api/src/retrieval/vector.py)                                                                                        | `EF_SEARCH` (100)                                                                                                                                                        |
| 4b  | **Full text:** the query is folded, stop words dropped, each word cut to a light stem (no root guessing), then matched as a prefix behind every clitic (و ف ب ك ل ال ...) on the `simple` tsvector with a GIN index. A text scores by the stems it holds, each weighted by BM25 IDF, so rare words win.                     | [query.py](../../apps/api/src/retrieval/query.py), [lexical.py](../../apps/api/src/retrieval/lexical.py)                                   | `MIN_STEM` (3), `MAX_TERMS` (8), `STOPWORDS`, `CLITIC_PREFIXES`. Trigram exists but the engine does not use it.                                                          |
| 4c  | **Concepts:** an in-memory inverted index over the model-written annotations of verses (about 6,000) and signals of hadiths (about 7,000); IDF-weighted stems, plus a bonus when two query words sit side by side in one concept. Built once per process, in a thread.                                                      | [concepts.py](../../apps/api/src/retrieval/concepts.py)                                                                                    | `PAIR_BONUS` (1.0)                                                                                                                                                       |
| 5   | **Reciprocal Rank Fusion** of every list (3 per query, plus anchors): a text at rank r earns `weight / (60 + r)` per list; only ranks are combined, never scores. Best 30 kept.                                                                                                                                             | [fusion.py](../../apps/api/src/retrieval/fusion.py)                                                                                        | `RRF_K` (60), per-list `weights` (all 1.0 today; the parameter exists, nothing sets it)                                                                                  |
| 6   | Documents of the 30 are loaded: folded text (chain of narrators cut from hadiths, 1,200 chars) followed by the concepts (500 chars). Same document is what was embedded.                                                                                                                                                    | [documents.py](../../apps/api/src/retrieval/documents.py)                                                                                  | `TEXT_MAX_CHARS`, `CONCEPTS_MAX_CHARS`, `TOPICS_PER_SIGNAL` (3)                                                                                                          |
| 7   | **Rerank** the first 8 of each list, all lists of the round at once. Default: a small LLM scores each numbered passage 0 to 10, answering numbers only (strict closed schema). On failure or timeout the fused order is kept and the reason logged.                                                                         | [reranker.py](../../apps/api/src/retrieval/reranker.py), `EvidenceSearch.rerank()`                                                         | `RERANK_TOP` (8), `RERANKER` = `llm` / `cross_encoder` / `off`, `rerank_model`, `reranker_timeout_seconds` (8). OVH has no rerank model, so there the fused order stays. |
| 8   | The first 4 of each corpus go to the verifier as `Q1..Q4`, `H1..H4`; it never sees or writes a stored id.                                                                                                                                                                                                                   | `shortlist_of()` in [evidence.py](../../apps/api/src/pipeline/insight/evidence.py)                                                         | `SHORTLIST` (4), `TEXT_CHARS` (700)                                                                                                                                      |
| 9   | **The gate:** a verse is always eligible; a hadith needs a recorded صحيح or حسن ruling, or counts as one of the enriched Sunnah file (decision 58). Strongest tier first, unseen before seen, reranker order breaks ties. A wanted hadith with no ruling is queued for an editor; the insight then carries its verse alone. | `gate()` in evidence.py, `_ranked()` in engine.py                                                                                          | `STRENGTH_ORDER`; learner order in learning.py (masar §10.4)                                                                                                             |
| 10  | Nothing passed: the failed candidates go back to the planner with their failed queries, at most two refinement rounds. As soon as one insight holds, the others are dropped.                                                                                                                                                | `_find_evidence()` in engine.py                                                                                                            | `rounds` of the engine                                                                                                                                                   |

Where the data comes from: the Quran (quranpedia, edition 2) and nine hadith books sit in the `corpus` schema; folded search copies in `quran_verse_search` and `hadith_search`; vectors in the `vectors` schema, one row per text, model and size (6,236 verses, 65,712 hadiths); concepts in `quran_annotations` and `hadith_signals`. Vectors are computed by `src.cli.embed_corpus`; a document's SHA-256 is stored with its vector, so a changed document is embedded again, that one only ([docs/EMBEDDINGS.md](../EMBEDDINGS.md)).

### What was measured (docs/BENCHMARK.md, retrieval)

- Embedding: `text-embedding-3-large` @ 1536 gives MRR@10 0.696 (OpenAI); `bge-m3` @ 1024 gives 0.601 (OVH).
- Full text MRR@10 0.219, trigram 0.133 (and 11 s p95), so trigram is unused.
- RRF of the three reaches recall@30 of 94 %, the most of any method, but ranks worse than the vector alone (MRR 0.564 against 0.696): that is the reason for the reranker.
- Rerank by `gpt-5.4-nano`: MRR 0.770, about 3 s. Cross-encoder `bge-reranker-v2-m3`: MRR 0.667, 19 s for 30 passages on this CPU.
- A scan takes about 22 s at p50 and 30 s at p95, about $0.02 (docs/EVALUATION.md).

### Where to improve later

Each lever says what to change and what to measure. Measure with `make benchmark` (retrieval section) and `make eval` before and after; record the numbers in docs/BENCHMARK.md and docs/EVALUATION.md.

| Lever                                           | Why it may help                                                                                                                                          | Where                                                                 |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Per-list RRF weights                            | Vector is the strongest single list (0.696) yet counts as much as full text (0.219); weighting it up could lift the fused MRR.                           | `weights` argument of `fuse()`, passed from `EvidenceSearch.search()` |
| Rerank more than 8, or use the verifier's score | Recall@30 is 94 % but only 8 are reranked and 4 verified; a right text at rank 9 to 30 is never seen. Cost is latency and tokens.                        | `RERANK_TOP`, `SHORTLIST`                                             |
| Better queries from the planner                 | Retrieval can only find what the queries say; the market scene drew an ablution verse. Several short queries per corpus beat one long one.               | planner prompt, task 05.3                                             |
| Query rewriting per corpus                      | Verse language and hadith language differ; the planner already splits the lists, its prompt could ask for wording of each.                               | planner prompt                                                        |
| Stemming and stop words                         | Light stems only; no roots. Add synonyms, or root matching, if full text misses morphological variants.                                                  | [query.py](../../apps/api/src/retrieval/query.py)                     |
| Richer documents                                | The concepts are what let modern Arabic find old Arabic; more or better concepts for texts that have none (hadiths: about 7,000 of 65,712 have signals). | `hadith_signals`, `quran_annotations`, then re-embed                  |
| Chunking of long hadiths                        | A document is cut at 1,200 chars, keeping the start; a subject that appears later is missed.                                                             | `TEXT_MAX_CHARS` in documents.py                                      |
| A rerank model on OVH                           | Without one an OVH scan keeps the fused order, which ranks worse.                                                                                        | `OvhSettings.rerank_model`, benchmark first                           |
| Cross-encoder on a GPU host                     | Best quality-per-token if latency stops being the problem.                                                                                               | `RERANKER=cross_encoder`, services/vision                             |
| Gold scenes                                     | Retrieval quality is judged on 15 scenes and the contest cases; more scenes with expected texts make a change provable.                                  | `apps/api/tests/evaluation/scenes/gold.json`                          |

## Steps

| Step                                                           | Status | Notes                                                      |
| -------------------------------------------------------------- | ------ | ---------------------------------------------------------- |
| Map of every prompt and where it is used                       | ✅     | 2026-10-05                                                 |
| Map of how search finds and ranks texts, and levers to improve | ✅     | 2026-10-05                                                 |
| Move `LLM_RERANK_SYSTEM` to a versioned prompt file            | ⬜     | Needs the owners' yes; small change.                       |
| Decide on old prompt versions (chat v2 to v4, composer v1)     | ⬜     | Keep as history or prune.                                  |
| Decide whether unhashed user-message builders matter           | ⬜     | Planner, verifier and composer messages are code.          |
| Planner prompt tuning: still phone, loose verses               | ⬜     | Task 05.3 in [05_insight_engine.md](05_insight_engine.md). |

**How we keep it current:** whenever a prompt file, a prompt constant or a search constant changes, update the tables above and the **Updated** time in the same commit (time from `date`, shown in Tunis time).
