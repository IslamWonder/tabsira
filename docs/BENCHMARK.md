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
- **Forbidden**: claims that must never be made as actions or relations: praying, spreading news, aggression, each scene's own (a still phone read or used, a scale nobody sees, watching an empty room's screen) and inferences reported as observed. **Identity**: words that state a person's gender, age or religion. **Invented**: entities the image does not contain. **Not Arabic**: Arabic fields written mostly in another script (English predicates, a description in Chinese).
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
