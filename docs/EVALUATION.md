# Evaluation: the insight engine on the gold scenes

Measured on 04 October 2026 by `make eval` (`apps/api/src/cli/evaluate.py`, `apps/api/src/evaluation/engine_eval.py`), with the real providers: openai (compose: `gpt-5.4-mini-2026-03-17`, embedding: `text-embedding-3-large`, planner: `gpt-5.4-mini-2026-03-17`, verify: `gpt-5.4-mini-2026-03-17`, vision: `gpt-5.4-mini-2026-03-17`). Raw results: `apps/api/tests/evaluation/results/evaluation-2026-10-04.json` (not committed). This file is written by that command.

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
| Hoped-for texts found                           | 3 / 9                   |
| Hadiths queued for an editor's ruling           | 24                      |
| Cost per scan                                   | $0.0187 (total $0.2811) |

Statuses: `no_relevant_evidence` 2, `ok` 13.

Relation types of the insights: `action_based` 1, `close_conceptual` 14, `direct` 4, `opposite` 1, `thematic_reminder` 12.

## Time per stage

| Stage                    | p50    | p95    |
| ------------------------ | ------ | ------ |
| understanding            | 3.6 s  | 4.2 s  |
| searching                | 23.7 s | 37.3 s |
| verifying                | 4.4 s  | 6.7 s  |
| composing                | 4.0 s  | 4.5 s  |
| vision (scene and guard) | 3.7 s  | 5.9 s  |
| whole scan               | 38.5 s | 58.7 s |

## Per scene

| Scene             | Expected | Status                 | As expected | Evidence                       | Relations                                              | Time   | Cost    |
| ----------------- | -------- | ---------------------- | ----------- | ------------------------------ | ------------------------------------------------------ | ------ | ------- |
| phone-alone       | abstain  | `ok`                   | no          | `Q:68:1`, `Q:62:11`, `Q:96:4`  | direct, close_conceptual, thematic_reminder            | 58.7 s | $0.0191 |
| phone-news        | insight  | `ok`                   | yes         | `Q:49:6`, `Q:4:71`, `Q:16:18`  | close_conceptual, close_conceptual, thematic_reminder  | 42.8 s | $0.0244 |
| market            | insight  | `ok`                   | yes         | `Q:5:6`, `Q:16:72`             | close_conceptual, thematic_reminder                    | 25.5 s | $0.0191 |
| child-cat         | insight  | `ok`                   | yes         | `Q:24:16`, `Q:13:4`            | close_conceptual, thematic_reminder                    | 68.1 s | $0.0311 |
| shared-meal       | insight  | `no_relevant_evidence` | no          | —                              | —                                                      | 8.8 s  | $0.0138 |
| book              | insight  | `ok`                   | yes         | `Q:39:22`, `Q:96:1`            | close_conceptual, close_conceptual                     | 48.9 s | $0.0229 |
| tv                | insight  | `ok`                   | yes         | `Q:6:99`, `Q:2:125`, `Q:24:35` | direct, close_conceptual, thematic_reminder            | 46.8 s | $0.0239 |
| rain              | insight  | `ok`                   | yes         | `Q:2:22`, `Q:30:50`, `Q:7:185` | direct, opposite, thematic_reminder                    | 37.7 s | $0.0193 |
| tree              | insight  | `ok`                   | yes         | `Q:7:58`, `Q:31:10`, `Q:5:16`  | close_conceptual, thematic_reminder, thematic_reminder | 41.0 s | $0.0181 |
| night-sky         | insight  | `ok`                   | yes         | `Q:91:5`                       | direct                                                 | 19.9 s | $0.0121 |
| hero              | insight  | `ok`                   | yes         | `Q:2:164`, `Q:36:40`           | close_conceptual, thematic_reminder                    | 24.0 s | $0.0163 |
| emblem            | abstain  | `no_relevant_evidence` | yes         | —                              | —                                                      | 3.5 s  | $0.0045 |
| rain-olive        | insight  | `ok`                   | yes         | `Q:6:99`, `Q:71:17`, `Q:7:58`  | action_based, close_conceptual, thematic_reminder      | 41.8 s | $0.0193 |
| glass-of-water    | insight  | `ok`                   | yes         | `Q:12:55`, `Q:6:99`, `Q:2:60`  | close_conceptual, close_conceptual, close_conceptual   | 38.5 s | $0.0202 |
| sensitive-alcohol | insight  | `ok`                   | yes         | `Q:7:31`, `Q:16:48`            | thematic_reminder, thematic_reminder                   | 29.7 s | $0.0172 |

## Limits

- Fifteen generated scenes, one run each: a p95 over so few samples is close to the maximum, and real photos may behave differently.
- No hadith has an editor's ruling yet (decision 18), so every insight carries its verse alone and the hadiths it wanted wait in the verification queue; the hadith half of the pipeline (relevance, queueing) runs, the display of a hadith does not.
- The checks are rules: they prove that no scripture leaked and that every reference is real, not that an explanation is good Arabic or a wise choice. Read the raw answers before trusting a small difference.

<!-- section:reranker-comparison -->

## With and without the cross-encoder

The run above sent the eight best fused candidates of every search to `BAAI/bge-reranker-v2-m3` on services/vision, on this machine's CPU. A second run the same day, with `RERANKER_URL=` empty (the fused order kept), gave (its raw results are not kept in the repository):

| Measure                    | With the reranker | Without         |
| -------------------------- | ----------------- | --------------- |
| Scenes handled as expected | 13 / 15           | 13 / 15         |
| Hoped-for texts found      | 3 / 9             | 1 / 9           |
| Searching, p50 / p95       | 23.7 s / 37.3 s   | 1.3 s / 8.1 s   |
| Whole scan, p50 / p95      | 38.5 s / 58.7 s   | 16.6 s / 28.4 s |
| Cost per scan              | $0.0187           | $0.0167         |

The cross-encoder finds the texts an editor expects more often, and it is the stage that puts a scan far over the 5 to 12 s target on a CPU: about 0.6 s per passage. Before production it needs a GPU (or a quantised model) on the vision host, or it is switched off with `RERANKER_URL=`. Without it, most of the time left is the scene analysis and the three model calls of the engine (planner, verifier, composer, about 4 s each with `gpt-5.4-mini`). With one run per scene, a single difference (the alcohol scene asked a question in the second run, the shared meal found no evidence in the first) is within the noise of the models.

What the runs show about quality, read from the raw answers: the phone lying alone, which should have led to a question, got three thematic insights in both runs (the planner does not yet treat «a still phone» as needing its use asked); several insights rest on general reminders (`thematic_reminder` 12 of 32) rather than a direct link; and some verses chosen are loose (the market scene drew a verse about ablution in the first run). The guard, the references and the abstention on the emblem hold; the choice of meaning needs work on the planner prompt and a human review of the gold scenes' expected texts.

<!-- /section:reranker-comparison -->
