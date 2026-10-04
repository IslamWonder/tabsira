# Evaluation: the insight engine on the gold scenes

Measured on 04 October 2026 by `make eval` (`apps/api/src/cli/evaluate.py`, `apps/api/src/evaluation/engine_eval.py`), with the real providers: openai (compose: `gpt-5.4-mini-2026-03-17`, embedding: `text-embedding-3-large`, planner: `gpt-5.4-mini-2026-03-17`, rerank: `gpt-5.4-nano-2026-03-17`, verify: `gpt-5.4-mini-2026-03-17`, vision: `gpt-5.4-mini-2026-03-17`). Raw results: `apps/api/tests/evaluation/results/evaluation-2026-10-04.json` (not committed). This file is written by that command.

## Method

- **Scenes**: the 15 gold scenes of `apps/api/tests/evaluation/scenes/gold.json` (generated images, not phone photos; see docs/BENCHMARK.md), each with what the engine should do in `engine-gold.json`: give an insight, or abstain (a question, or no insight).
- **Pipeline per scene**: image check, the detector of services/vision (available for 15 of 15 scenes; without it the scene is described without boxes), scene analysis and the sensitivity guard, then the insight engine: ontology and constraints, learning path, planner, hybrid search and rerank, verifier and evidence gate, composer.
- **Checks, by rule**: every text of every insight through the scripture guard (patterns, the whole Quran, the hadiths shown); every evidence reference resolved to a stored text whose SHA-256 still matches its bytes; the relation types; abstention where expected; the hoped-for texts (informational: other texts can be as good).

## Results

| Measure                                         | Result                  |
| ----------------------------------------------- | ----------------------- |
| Scripture leakage (texts refused by the guard)  | 0                       |
| Evidence references resolvable and hash-checked | 32 / 32                 |
| Scenes handled as expected                      | 13 / 15                 |
| Abstention where expected                       | 1 / 2                   |
| Insight where expected                          | 12 / 13                 |
| Hoped-for texts found                           | 1 / 9                   |
| Hadiths queued for an editor's ruling           | 23                      |
| Cost per scan                                   | $0.0204 (total $0.3063) |

Statuses: `no_relevant_evidence` 2, `ok` 13.

Relation types of the insights: `close_conceptual` 14, `direct` 1, `opposite` 1, `thematic_reminder` 16.

## Time per stage

| Stage                    | p50    | p95    |
| ------------------------ | ------ | ------ |
| understanding            | 4.3 s  | 5.1 s  |
| searching                | 4.1 s  | 9.5 s  |
| verifying                | 5.4 s  | 6.0 s  |
| composing                | 4.5 s  | 5.8 s  |
| vision (scene and guard) | 4.7 s  | 7.2 s  |
| whole scan               | 21.7 s | 30.5 s |

## Per scene

| Scene             | Expected | Status                 | As expected | Evidence                        | Relations                                              | Time   | Cost    |
| ----------------- | -------- | ---------------------- | ----------- | ------------------------------- | ------------------------------------------------------ | ------ | ------- |
| phone-alone       | abstain  | `ok`                   | no          | `Q:96:4`, `Q:45:12`, `Q:4:71`   | close_conceptual, thematic_reminder, thematic_reminder | 30.5 s | $0.0210 |
| phone-news        | insight  | `ok`                   | yes         | `Q:17:36`, `Q:54:35`            | close_conceptual, thematic_reminder                    | 21.3 s | $0.0232 |
| market            | insight  | `ok`                   | yes         | `Q:6:141`                       | thematic_reminder                                      | 20.5 s | $0.0188 |
| child-cat         | insight  | `ok`                   | yes         | `Q:16:48`, `Q:6:99`             | thematic_reminder, thematic_reminder                   | 40.0 s | $0.0343 |
| shared-meal       | insight  | `ok`                   | yes         | `Q:76:8`, `Q:2:172`, `Q:5:88`   | close_conceptual, thematic_reminder, thematic_reminder | 27.6 s | $0.0287 |
| book              | insight  | `ok`                   | yes         | `Q:18:66`                       | thematic_reminder                                      | 17.5 s | $0.0142 |
| tv                | insight  | `ok`                   | yes         | `Q:6:99`, `Q:96:3`, `Q:16:80`   | close_conceptual, close_conceptual, thematic_reminder  | 24.3 s | $0.0260 |
| rain              | insight  | `ok`                   | yes         | `Q:16:65`, `Q:2:164`, `Q:79:32` | close_conceptual, close_conceptual, thematic_reminder  | 20.1 s | $0.0191 |
| tree              | insight  | `ok`                   | yes         | `Q:2:153`, `Q:3:191`, `Q:24:44` | close_conceptual, thematic_reminder, thematic_reminder | 21.7 s | $0.0180 |
| night-sky         | insight  | `ok`                   | yes         | `Q:10:67`, `Q:7:54`             | close_conceptual, thematic_reminder                    | 21.6 s | $0.0188 |
| hero              | insight  | `ok`                   | yes         | `Q:2:164`, `Q:14:1`, `Q:3:191`  | close_conceptual, opposite, thematic_reminder          | 23.0 s | $0.0240 |
| emblem            | abstain  | `no_relevant_evidence` | yes         | —                               | —                                                      | 4.9 s  | $0.0044 |
| rain-olive        | insight  | `ok`                   | yes         | `Q:39:21`, `Q:41:39`, `Q:6:99`  | direct, close_conceptual, close_conceptual             | 27.4 s | $0.0245 |
| glass-of-water    | insight  | `ok`                   | yes         | `Q:23:18`, `Q:6:99`, `Q:43:13`  | close_conceptual, close_conceptual, thematic_reminder  | 24.4 s | $0.0243 |
| sensitive-alcohol | insight  | `no_relevant_evidence` | no          | —                               | —                                                      | 6.1 s  | $0.0071 |

## Limits

- Fifteen generated scenes, one run each: a p95 over so few samples is close to the maximum, and real photos may behave differently.
- No hadith has an editor's ruling yet (decision 18), so every insight carries its verse alone and the hadiths it wanted wait in the verification queue; the hadith half of the pipeline (relevance, queueing) runs, the display of a hadith does not.
- The checks are rules: they prove that no scripture leaked and that every reference is real, not that an explanation is good Arabic or a wise choice. Read the raw answers before trusting a small difference.

<!-- section:reranker-comparison -->

## Reranker: small model, cross-encoder, none

The run above is the default since decision 41 (`RERANKER=llm`): `gpt-5.4-nano` scores the eight best fused candidates of every search, all the searches of a round at once, with an 8 s limit and the fused order kept on failure. Two earlier runs the same day used the cross-encoder `BAAI/bge-reranker-v2-m3` on services/vision, on this machine's CPU, and no reranker (their raw results are not kept in the repository):

| Measure                        | Small model (default) | Cross-encoder (CPU) | None            |
| ------------------------------ | --------------------- | ------------------- | --------------- |
| Scenes handled as expected     | 13 / 15               | 13 / 15             | 13 / 15         |
| Hoped-for texts found          | 1 / 9                 | 3 / 9               | 1 / 9           |
| `direct` / `thematic_reminder` | 1 / 16 of 32          | 4 / 12 of 32        | not kept        |
| Searching, p50 / p95           | 4.1 s / 9.5 s         | 23.7 s / 37.3 s     | 1.3 s / 8.1 s   |
| Whole scan, p50 / p95          | 21.7 s / 30.5 s       | 38.5 s / 58.7 s     | 16.6 s / 28.4 s |
| Cost per scan                  | $0.0204               | $0.0187             | $0.0167         |

The small model costs about 2.8 s of searching at p50 (4.1 s against 1.3 s without a reranker) and $0.002 a scan; the cross-encoder cost 22 s on a CPU. It did not find more of the hoped-for texts here: one of nine, like no reranker, where the cross-encoder run found three. On the 109 gold queries of the retrieval benchmark the small model ranks best of the three (MRR 0.770 against 0.667 for the cross-encoder, docs/BENCHMARK.md), so with one run per scene and nine hoped-for texts the difference is more likely the planner's queries and the verifier varying between runs than the reranker; it is not proven either way. The relation types moved the wrong way in this run (more `thematic_reminder`), which task 05.3 takes up.

**Where the time goes.** The whole scan is still above 15 s at p50 (21.7 s). It is five model calls in a row: the scene and its guard (4.7 s), the planner (4.3 s), the reranker (about 2.8 s, one wait for all lists), the verifier (5.4 s) and the composer (4.5 s); the embedding of the queries and the database searches take about 1.3 s together. The same four calls were 0.5 to 1 s faster each in the cross-encoder run, so part of the 5 s gap to the run without a reranker is likely the provider's latency of the hour, not the reranker. Under 15 s needs one of these calls to go or to overlap another: the verifier and the reranker both judge relevance, and the composer could start on the first candidate that passes while the others are checked. These are not done here.

What the runs show about quality, read from the raw answers: the phone lying alone, which should have led to a question, got three thematic insights in every run (the planner does not yet treat «a still phone» as needing its use asked); several insights rest on general reminders rather than a direct link; and some verses chosen are loose (the market scene drew a verse about ablution in the cross-encoder run). The guard, the references and the abstention on the emblem hold in all three; the choice of meaning needs work on the planner prompt and a human review of the gold scenes' expected texts (task 05.3).

<!-- /section:reranker-comparison -->
