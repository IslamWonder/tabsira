# Benchmark: scene analysis

Measured on 04 October 2026 by `make benchmark` (`apps/api/src/cli/benchmark.py`), in 17 minutes. This file is written by the benchmark; every answer and call record is in `apps/api/tests/evaluation/results/2026-10-04.json` (not committed), and the per-cell numbers in the summary file next to it. Decision 4 of `docs/spec/DECISIONS.md`: the measured result sets the default model of each stage.

## Method

- **Scenes**: 15 gold scenes from `apps/api/tests/evaluation/scenes/gold.json`, each with the entities a description must name, the actions it should report, the claims it must not make and whether it is sensitive (1 sensitive). None of these images is a photograph. The twelve demo images and rain-olive.jpg were generated with the Freepik text-to-image API by the old demo's scripts (scripts/generate-demo-images.ts and scripts/generate-tabsirah-images.ts); each prompt is recorded with its scene in gold.json. glass-of-water.jpg and sensitive-alcohol.jpg have no generation record in the old repository; their 1344x768 JFIF files without camera EXIF match the generated set, so they are most likely generated too. Licence: Freepik's terms for AI-generated content, not verified.
- **Runs**: each scene 2 times through each cell, plus 1 blind run(s) with the detector hidden from the model (for the boxes only).
- **Pipeline per scene**: the image validator (once), the detector of `services/vision` (once; `yoloe-11s-seg`, available for 15 of 15 scenes), then for every cell and run the scene analyzer (the vision model sees the image and the detector's boxes) and the sensitivity guard (the scene's own flags, plus `omni-moderation-latest` on the image for OpenAI cells).
- **Prompt**: `scene_analyzer_system.v1@519cf593ab12+scene_analyzer_user.v1@2f226497316c`.
- **Call limits**: the configured `AI_TIMEOUT_SECONDS`, `AI_MAX_RETRIES` and `AI_RETRY_BACKOFF_SECONDS`; latency is the wall time of a call, retries included.

Cells:

| Cell                       | Provider | Model                     | Reasoning        | Boxes       | Guard                    | Role                                    |
| -------------------------- | -------- | ------------------------- | ---------------- | ----------- | ------------------------ | --------------------------------------- |
| `ovh-qwen3.8-27b-thinking` | ovh      | `Qwen3.8-27B`             | provider default | thousandths | scene flags only         | primary, thinking on (provider default) |
| `ovh-qwen3.8-27b`          | ovh      | `Qwen3.8-27B`             | none             | thousandths | scene flags only         | primary, thinking off                   |
| `ovh-qwen3.8-27b-pixels`   | ovh      | `Qwen3.8-27B`             | none             | pixels      | scene flags only         | variant: boxes asked in pixels          |
| `ovh-qwen3.5-9b`           | ovh      | `Qwen3.5-9B`              | none             | thousandths | scene flags only         | smaller challenger                      |
| `openai-gpt-5.4-mini`      | openai   | `gpt-5.4-mini-2026-03-17` | none             | pixels      | `omni-moderation-latest` | primary, no reasoning                   |
| `openai-gpt-5.4-mini-low`  | openai   | `gpt-5.4-mini-2026-03-17` | low              | pixels      | `omni-moderation-latest` | variant: low reasoning                  |
| `openai-gpt-5.4-nano`      | openai   | `gpt-5.4-nano-2026-03-17` | none             | pixels      | `omni-moderation-latest` | smaller challenger                      |

Metrics, scored by rule (`apps/api/src/evaluation/scoring.py`; patterns are matched on normalised Arabic and English words):

- **Runs**: runs measured out of those planned. A run skipped by the spend cap, or whose call never reached the provider (a network fault on our side, listed under the findings), is not measured.
- **Valid**: runs whose answer matched the JSON schema after the bounded retries; **first try**: without a retry.
- **Entity recall**: share of the required entities named in the description or the entity labels. **Action recall**: share of the expected actions found among the reported actions and relations, over the scenes that expect one.
- **Forbidden**: claims that must never be made as actions or relations: praying, spreading news, aggression, each scene's own (a still phone read or used, a scale nobody sees, watching an empty room's screen) and inferences reported as observed. **Identity**: words that state a person's gender, age or religion, counted even when the scene stage already replaced them by «شخص» (the model still wrote them; the replacement note carries the word). **Invented**: entities the image does not contain. **Not Arabic**: Arabic fields written mostly in another script (English predicates, a description in Chinese).
- **Sensitive**: the guard's verdict against the gold scene; FN a sensitive scene missed, FP an ordinary scene flagged. **Question**: a clarification asked exactly when the gold scene expects one.
- **Boxes out**: model boxes outside the image, dropped by the server. **IoU vs detector**: median overlap between the model's box and the detector's box for the entities the model matched to a detection. Given the detector's boxes, models mostly copy them, so this only checks consistency; the blind runs below show where a model's own boxes land.
- **Quality** = valid x sensitive accuracy x entity recall / (1 + violations per run), the violations being forbidden, identity, invented and not Arabic.

Choice of a default: a cell is eligible when at least 90% of its answers are valid, it misses no sensitive scene, at most 20% of its boxes fall outside the image (with or without the detector) and its median IoU with the detector is at least 0.5. Among eligible cells within 0.05 of the best quality, the lowest vision p95 wins, then the lowest cost per scan.

## Results

| Cell                       | Runs  | Valid | First try | Entity recall | Action recall | Forbidden | Identity | Invented | Not Arabic | Sensitive (FN/FP) | Question | Boxes out | IoU vs detector | Quality             |
| -------------------------- | ----- | ----- | --------- | ------------- | ------------- | --------- | -------- | -------- | ---------- | ----------------- | -------- | --------- | --------------- | ------------------- |
| `ovh-qwen3.8-27b-thinking` | 30/30 | 93%   | 80%       | 100%          | 88%           | 0         | 0        | 0        | 0          | 100% (0/0)        | 0%       | 0%        | 0.99            | 0.93                |
| `ovh-qwen3.8-27b`          | 30/30 | 100%  | 100%      | 100%          | 70%           | 1         | 0        | 0        | 0          | 100% (0/0)        | 0%       | 0%        | 0.87            | 0.97                |
| `ovh-qwen3.8-27b-pixels`   | 30/30 | 100%  | 97%       | 99%           | 70%           | 0         | 0        | 0        | 1          | 100% (0/0)        | 50%      | 13%       | 0.81            | 0.96 (not eligible) |
| `ovh-qwen3.5-9b`           | 30/30 | 100%  | 93%       | 91%           | 40%           | 0         | 1        | 0        | 59         | 83% (0/5)         | 50%      | 4%        | 0.98            | 0.25                |
| `openai-gpt-5.4-mini`      | 30/30 | 100%  | 100%      | 98%           | 80%           | 0         | 0        | 0        | 0          | 100% (0/0)        | 0%       | 0%        | 0.99            | 0.98                |
| `openai-gpt-5.4-mini-low`  | 30/30 | 100%  | 100%      | 98%           | 90%           | 0         | 0        | 0        | 0          | 100% (0/0)        | 0%       | 0%        | 0.99            | 0.98                |
| `openai-gpt-5.4-nano`      | 30/30 | 100%  | 100%      | 94%           | 70%           | 1         | 0        | 0        | 0          | 97% (1/0)         | 50%      | 0%        | 1.00            | 0.88 (not eligible) |

| Cell                       | Vision p50 | Vision p95 | Guard p50 | Guard p95 | Input tokens | Output tokens | of which reasoning | Cost per scan | Cell total |
| -------------------------- | ---------- | ---------- | --------- | --------- | ------------ | ------------- | ------------------ | ------------- | ---------- |
| `ovh-qwen3.8-27b-thinking` | 46.5 s     | 179.4 s    | n/a       | n/a       | 2412         | 3618          | 2513               | $0.0127       | $0.5590    |
| `ovh-qwen3.8-27b`          | 10.6 s     | 27.1 s     | n/a       | n/a       | 2485         | 1053          | 0                  | $0.0045       | $0.2038    |
| `ovh-qwen3.8-27b-pixels`   | 12.2 s     | 42.2 s     | n/a       | n/a       | 2474         | 1054          | 0                  | $0.0045       | $0.2066    |
| `ovh-qwen3.5-9b`           | 24.8 s     | 106.3 s    | n/a       | n/a       | 2485         | 1027          | 0                  | $0.0005       | $0.0211    |
| `openai-gpt-5.4-mini`      | 3.7 s      | 5.7 s      | 0.5 s     | 0.9 s     | 3372         | 575           | 0                  | $0.0033       | $0.1520    |
| `openai-gpt-5.4-mini-low`  | 4.3 s      | 6.5 s      | 0.4 s     | 1.3 s     | 3372         | 686           | 78                 | $0.0039       | $0.1754    |
| `openai-gpt-5.4-nano`      | 5.1 s      | 9.5 s      | 0.4 s     | 0.9 s     | 3372         | 686           | 0                  | $0.0012       | $0.0580    |

Boxes with the detector hidden (blind runs): how many boxes the model gave, how many fell outside the image, and how many land on a box of the detector (IoU at least 0.5 with one of them; the detector finds only some of the things a model names, so 100% is not expected, but a wrong coordinate system shows as a collapse):

| Cell                       | Asked in    | Runs | Boxes | Outside | On a detector box | Median best IoU |
| -------------------------- | ----------- | ---- | ----- | ------- | ----------------- | --------------- |
| `ovh-qwen3.8-27b-thinking` | thousandths | 15   | 120   | 0%      | 42%               | 0.27            |
| `ovh-qwen3.8-27b`          | thousandths | 15   | 109   | 0%      | 45%               | 0.31            |
| `ovh-qwen3.8-27b-pixels`   | pixels      | 15   | 108   | 31%     | 18%               | 0.15            |
| `ovh-qwen3.5-9b`           | thousandths | 15   | 92    | 5%      | 33%               | 0.21            |
| `openai-gpt-5.4-mini`      | pixels      | 15   | 79    | 0%      | 41%               | 0.32            |
| `openai-gpt-5.4-mini-low`  | pixels      | 15   | 81    | 0%      | 41%               | 0.41            |
| `openai-gpt-5.4-nano`      | pixels      | 15   | 71    | 3%      | 36%               | 0.33            |

Stages run once per scene:

| Stage                | Samples | p50   | p95   | Mean  |
| -------------------- | ------- | ----- | ----- | ----- |
| Image validation     | 15      | 0.0 s | 0.1 s | 0.0 s |
| Detector (HTTP, CPU) | 15      | 2.4 s | 7.2 s | 3.3 s |

## What the judge found

Most frequent findings per cell, with their count over all runs:

- `ovh-qwen3.8-27b-thinking`: nothing.
  Failed runs: timeout (1); truncated (1).
- `ovh-qwen3.8-27b`: reported as observed: «يقرا» (1).
- `ovh-qwen3.8-27b-pixels`: missing: «شمس» (1); not in Arabic: clarification_question (1).
  Not eligible: 31% of boxes outside the image.
- `ovh-qwen3.5-9b`: not in Arabic: relations (31); not in Arabic: actions (14); not in Arabic: ambiguities (11); missing: «ارز» (2); missing: «جذور» (2); identity word: «children» (1).
- `openai-gpt-5.4-mini`: missing: «جذور» (2).
- `openai-gpt-5.4-mini-low`: missing: «جذور» (2).
- `openai-gpt-5.4-nano`: missing: «ماء» (3); missing: «ارز» (2); missing: «جريده» (2); praying (a rug and a bent posture do not prove prayer): «يركع» (1).
  Not eligible: missed 1 sensitive scene(s).

## Recommended defaults

| Setting                       | Value                     | Why                                                                                                                                                                                                                                             |
| ----------------------------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AI_PROVIDER`                 | `openai`                  | openai-gpt-5.4-mini: quality 0.98, entity recall 98%, 0.00 violations per run, vision p95 5673 ms, $0.0033 per scan (against ovh-qwen3.8-27b: quality 0.97, entity recall 100%, 0.03 violations per run, vision p95 27137 ms, $0.0045 per scan) |
| `AI_OVH__VISION_MODEL`        | `Qwen3.8-27B`             | ovh-qwen3.8-27b: quality 0.97, entity recall 100%, 0.03 violations per run, vision p95 27137 ms, $0.0045 per scan                                                                                                                               |
| `AI_OVH__REASONING_EFFORT`    | `none`                    | the setting of ovh-qwen3.8-27b                                                                                                                                                                                                                  |
| `AI_OVH__BOX_COORDINATES`     | `thousandths`             | thousandths: with the detector hidden, 0% of boxes outside the image and 45% on a detector box; pixels: with the detector hidden, 31% of boxes outside the image and 18% on a detector box                                                      |
| `AI_OPENAI__VISION_MODEL`     | `gpt-5.4-mini-2026-03-17` | openai-gpt-5.4-mini: quality 0.98, entity recall 98%, 0.00 violations per run, vision p95 5673 ms, $0.0033 per scan                                                                                                                             |
| `AI_OPENAI__REASONING_EFFORT` | `none`                    | the setting of openai-gpt-5.4-mini                                                                                                                                                                                                              |
| `AI_OPENAI__BOX_COORDINATES`  | `pixels`                  | pixels: with the detector hidden, 0% of boxes outside the image and 41% on a detector box                                                                                                                                                       |
| `AI_OPENAI__GUARD_MODEL`      | `omni-moderation-latest`  | image moderation p95 876 ms over 30 calls, 0 false positive(s)                                                                                                                                                                                  |

## Limits

- The scenes are generated images, not photos from phones; real photos (noise, blur, odd framing, faces) may change the ranking.
- 15 scenes with 1 sensitive: the sensitivity numbers show false positives and a missed alcohol scene, not the recall of nudity, drugs, gambling or violence. `omni-moderation-latest` classifies images for sexual content, violence and self-harm only.
- No scene shows a rug and a bent posture or a raised hand: those rules are checked as claims that must never appear, not on images built to tempt them.
- The judge works by word patterns. It does not grade the Arabic, and it cannot tell a correct description written in unexpected words from a wrong one; read the raw answers before trusting a small difference.
- 2 runs per scene: a p95 over so few samples is close to the maximum.

## Spend

Total model spend of this run: **$1.3758** (prices of `AI_*__PRICES`; moderation is free).

<!-- section:retrieval -->

## Benchmark: retrieval

Measured on 04 October 2026 by `uv run python -m src.cli.retrieval_benchmark` (`apps/api/src/evaluation/retrieval_benchmark.py`). Raw ranks: `apps/api/tests/evaluation/results/retrieval-2026-10-04.json` (not committed). This section is rewritten by that command; the scene benchmark keeps it.

### Method

- **Gold set**: `apps/api/tests/evaluation/retrieval/gold.json`, 109 Arabic concept queries written the way the planner writes them (69 Quran, 40 hadith), each with the stored texts that answer it: the anchors of the learning path, the texts the gold scenes call for, and well-known hadiths whose stored numbers were found by searching their distinctive words. No query quotes scripture. Hadith queries are judged against bukhari, muslim only, so every embedding model sees the same 14,940 hadiths and the whole Quran.
- **Documents**: the folded search copy of each text (a hadith without its chain) followed by its model-written concepts (`src/retrieval/documents.py`); never displayed.
- **Methods**: vector search per embedding cell (exact scan), PostgreSQL full text (`fts`, `simple` configuration, stems matched behind every clitic) and pg_trgm word similarity (`trigram`), the concept index, their RRF fusions (k = 60), and the rerankers on the 30 fused candidates of `hybrid+concepts:openai-3-large`. `+metadata` is the earlier build's recipe: 0.6 x (0.7 x reranker + 0.3 x share of the query's stems in the text's concepts) + 0.4 x fused score.
- **Metrics**: recall@k = share of queries with an answer in the first k; MRR@10 = mean of 1/rank of the first answer, 0 past ten. One acceptable answer per query while the corpus may hold others as good: these numbers are lower bounds, fit for comparing methods.

| Cell             | Provider | Model                    | Dimensions |
| ---------------- | -------- | ------------------------ | ---------- |
| `openai-3-small` | openai   | `text-embedding-3-small` | 1536       |
| `openai-3-large` | openai   | `text-embedding-3-large` | 1536       |
| `ovh-bge-m3`     | ovh      | `bge-m3`                 | 1024       |

### Results (all queries)

| Method                                        | Corpus | R@1 | R@3 | R@10 | R@30 | MRR@10 |
| --------------------------------------------- | ------ | --- | --- | ---- | ---- | ------ |
| `rerank:llm-gpt-5.4-nano-2026-03-17`          | all    | 68% | 84% | 92%  | 94%  | 0.770  |
| `rerank:llm-gpt-5.4-nano-2026-03-17+metadata` | all    | 58% | 82% | 90%  | 94%  | 0.703  |
| `vector:openai-3-large`                       | all    | 62% | 76% | 83%  | 89%  | 0.696  |
| `rerank:bge-reranker-v2-m3`                   | all    | 55% | 80% | 86%  | 94%  | 0.667  |
| `rerank:bge-reranker-v2-m3+metadata`          | all    | 51% | 74% | 85%  | 94%  | 0.638  |
| `vector:ovh-bge-m3`                           | all    | 53% | 65% | 74%  | 79%  | 0.601  |
| `rerank:amberoad-msmarco+metadata`            | all    | 44% | 69% | 83%  | 94%  | 0.585  |
| `rerank:amberoad-msmarco`                     | all    | 46% | 68% | 83%  | 94%  | 0.583  |
| `hybrid+concepts:openai-3-large`              | all    | 41% | 67% | 85%  | 94%  | 0.564  |
| `hybrid+concepts:ovh-bge-m3`                  | all    | 37% | 64% | 77%  | 85%  | 0.513  |
| `hybrid:openai-3-large`                       | all    | 34% | 61% | 86%  | 91%  | 0.511  |
| `hybrid+concepts:openai-3-small`              | all    | 35% | 54% | 73%  | 84%  | 0.465  |
| `hybrid:ovh-bge-m3`                           | all    | 28% | 58% | 76%  | 81%  | 0.436  |
| `concepts`                                    | all    | 32% | 52% | 64%  | 78%  | 0.429  |
| `vector:openai-3-small`                       | all    | 32% | 43% | 60%  | 74%  | 0.399  |
| `hybrid:openai-3-small`                       | all    | 24% | 44% | 63%  | 73%  | 0.360  |
| `fts`                                         | all    | 17% | 27% | 31%  | 39%  | 0.219  |
| `trigram`                                     | all    | 11% | 14% | 20%  | 32%  | 0.133  |

### Results by corpus

| Method                                        | Corpus | R@1 | R@3 | R@10 | R@30 | MRR@10 |
| --------------------------------------------- | ------ | --- | --- | ---- | ---- | ------ |
| `rerank:llm-gpt-5.4-nano-2026-03-17`          | hadith | 62% | 85% | 90%  | 90%  | 0.738  |
| `rerank:llm-gpt-5.4-nano-2026-03-17+metadata` | hadith | 57% | 88% | 90%  | 90%  | 0.722  |
| `vector:openai-3-large`                       | hadith | 62% | 80% | 82%  | 85%  | 0.705  |
| `rerank:bge-reranker-v2-m3+metadata`          | hadith | 55% | 82% | 82%  | 90%  | 0.671  |
| `rerank:bge-reranker-v2-m3`                   | hadith | 55% | 80% | 85%  | 90%  | 0.662  |
| `rerank:amberoad-msmarco`                     | hadith | 55% | 80% | 85%  | 90%  | 0.660  |
| `rerank:amberoad-msmarco+metadata`            | hadith | 48% | 78% | 82%  | 90%  | 0.617  |
| `hybrid+concepts:openai-3-large`              | hadith | 48% | 70% | 85%  | 90%  | 0.605  |
| `vector:ovh-bge-m3`                           | hadith | 48% | 60% | 65%  | 70%  | 0.542  |
| `hybrid+concepts:ovh-bge-m3`                  | hadith | 40% | 68% | 75%  | 82%  | 0.538  |
| `hybrid:openai-3-large`                       | hadith | 32% | 68% | 85%  | 88%  | 0.532  |
| `concepts`                                    | hadith | 35% | 55% | 72%  | 80%  | 0.465  |
| `hybrid:ovh-bge-m3`                           | hadith | 30% | 57% | 70%  | 70%  | 0.446  |
| `hybrid+concepts:openai-3-small`              | hadith | 25% | 55% | 68%  | 82%  | 0.405  |
| `hybrid:openai-3-small`                       | hadith | 25% | 45% | 55%  | 68%  | 0.360  |
| `vector:openai-3-small`                       | hadith | 30% | 40% | 55%  | 68%  | 0.360  |
| `fts`                                         | hadith | 22% | 30% | 38%  | 38%  | 0.272  |
| `trigram`                                     | hadith | 10% | 10% | 18%  | 28%  | 0.114  |
| `rerank:llm-gpt-5.4-nano-2026-03-17`          | quran  | 71% | 84% | 93%  | 96%  | 0.789  |
| `rerank:llm-gpt-5.4-nano-2026-03-17+metadata` | quran  | 58% | 78% | 90%  | 96%  | 0.692  |
| `vector:openai-3-large`                       | quran  | 62% | 74% | 83%  | 91%  | 0.691  |
| `rerank:bge-reranker-v2-m3`                   | quran  | 55% | 80% | 87%  | 96%  | 0.670  |
| `vector:ovh-bge-m3`                           | quran  | 57% | 68% | 80%  | 84%  | 0.635  |
| `rerank:bge-reranker-v2-m3+metadata`          | quran  | 49% | 70% | 87%  | 96%  | 0.619  |
| `rerank:amberoad-msmarco+metadata`            | quran  | 42% | 64% | 84%  | 96%  | 0.567  |
| `hybrid+concepts:openai-3-large`              | quran  | 38% | 65% | 86%  | 96%  | 0.540  |
| `rerank:amberoad-msmarco`                     | quran  | 41% | 61% | 83%  | 96%  | 0.538  |
| `hybrid+concepts:openai-3-small`              | quran  | 41% | 54% | 77%  | 86%  | 0.500  |
| `hybrid:openai-3-large`                       | quran  | 35% | 58% | 87%  | 93%  | 0.499  |
| `hybrid+concepts:ovh-bge-m3`                  | quran  | 35% | 62% | 78%  | 87%  | 0.499  |
| `hybrid:ovh-bge-m3`                           | quran  | 26% | 58% | 80%  | 87%  | 0.430  |
| `vector:openai-3-small`                       | quran  | 33% | 45% | 62%  | 78%  | 0.422  |
| `concepts`                                    | quran  | 30% | 51% | 59%  | 77%  | 0.408  |
| `hybrid:openai-3-small`                       | quran  | 23% | 43% | 68%  | 77%  | 0.360  |
| `fts`                                         | quran  | 14% | 25% | 28%  | 41%  | 0.189  |
| `trigram`                                     | quran  | 12% | 16% | 22%  | 35%  | 0.144  |

### Latency (this machine, CPU)

| Step                                   | Samples | p50      | p95      |
| -------------------------------------- | ------- | -------- | -------- |
| embed one query: openai-3-small        | 5       | 254 ms   | 1137 ms  |
| embed one query: ovh-bge-m3            | 5       | 163 ms   | 192 ms   |
| search: trigram                        | 109     | 707 ms   | 11042 ms |
| search: vector openai-3-small          | 109     | 49 ms    | 89 ms    |
| search: vector ovh-bge-m3              | 109     | 24 ms    | 274 ms   |
| rerank 30: bge-reranker-v2-m3          | 109     | 19409 ms | 34235 ms |
| rerank 30: llm-gpt-5.4-nano-2026-03-17 | 109     | 3046 ms  | 3670 ms  |
| embed one query: openai-3-large        | 5       | 273 ms   | 807 ms   |
| search: fts                            | 109     | 97 ms    | 379 ms   |
| search: concepts                       | 109     | 5 ms     | 10 ms    |
| search: vector openai-3-large          | 109     | 6 ms     | 12 ms    |
| rerank 30: amberoad-msmarco            | 109     | 5285 ms  | 6771 ms  |

### Choices

| Setting            | Choice                          | Measured                    |
| ------------------ | ------------------------------- | --------------------------- |
| embedding (openai) | `text-embedding-3-large` @ 1536 | MRR@10 0.696, recall@10 83% |
| embedding (ovh)    | `bge-m3` @ 1024                 | MRR@10 0.601, recall@10 74% |
| lexical search     | `fts`                           | MRR@10 0.219                |
| reranker           | `bge-reranker-v2-m3`            | MRR@10 0.667, recall@3 80%  |

Spend of the runs merged here: **$0.1484** (query embeddings and the LLM rerank baseline; the corpus vectors were paid by `src.cli.embed_corpus`, see `vectors.embedding_runs`).
<!-- /section:retrieval -->

<!-- section:retrieval-notes -->

## Retrieval: what the numbers decided

Written by hand from the retrieval section above (4 October 2026); the commands keep it.

- **Embedding.** `text-embedding-3-large` at 1,536 dimensions is the clear best (MRR@10 0.696 against 0.601 for OVH's `bge-m3` and 0.399 for `text-embedding-3-small`, which is weak on Arabic concept queries). It is the OpenAI default; `bge-m3` is the OVH default, so switching `AI_PROVIDER` keeps semantic search. 1,536 rather than 3,072 dimensions so pgvector can index it with HNSW (2,000 at most). Embedding the whole store cost $2.03 (`docs/ASSET_MANIFEST.md` §11).
- **Lexical search.** PostgreSQL full text beats pg_trgm on quality (MRR@10 0.219 against 0.133) and on time (p95 0.45 s against 11 s over the hadiths), so the search copies carry a `tsvector` with a GIN index and trigram search is not used by the engine.
- **Fusion.** Vector, full text and the model-written concepts fused by RRF reach recall@30 94 %, the most of any method, so the reranker and the verifier see more right answers; the fused order alone ranks worse than the vector alone (MRR 0.564 against 0.696), which is what the reranker is for.
- **Reranker.** The LLM baseline (`gpt-5.4-nano`) ranks best of all (MRR 0.770, recall@3 84 %) in about 3 s, so it is the default (decision 41, `RERANKER=llm`): the engine sends it the eight best fused candidates of each search, all the searches of a round at once, and reads back numbers and scores only. In the gold-scene evaluation it adds about 2.8 s and $0.002 to a scan (whole scan 21.7 s at p50, 30.5 s at p95, $0.0204; docs/EVALUATION.md). OVH has no small text model measured for this, so on OVH `RERANKER=llm` keeps the fused order. Of the two cross-encoders, `BAAI/bge-reranker-v2-m3` wins clearly over the reference `amberoad/bert-multilingual-passage-reranking-msmarco` (MRR 0.667 against 0.583, recall@3 80 % against 68 %), and the reference file's metadata blend makes both worse, so it is not used. `bge-reranker-v2-m3` is the model services/vision serves for `RERANKER=cross_encoder`, for a host with a GPU: on this CPU it reads 30 passages in 19 s at p50 (34 s at p95), and even eight per search made a scan 38.5 s at p50.

<!-- /section:retrieval-notes -->
