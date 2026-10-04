# AI providers — capability research

Input to `make benchmark` (decision 4, v2 §22). It lists candidates per stage; it does **not** choose defaults. The benchmark does.

- Research date: 4 October 2026.
- "Verified live" means one call made on that date with the project keys, from a development machine; latencies are a single wall-clock sample (TLS set-up included), not p50/p95.
- "Documented" means read from the provider's catalogue or docs and not exercised.
- Excluded by project rule (AGENTS.md): the gpt-oss family. It is not listed below.

## 1. Endpoints

| Provider              | Base URL (OpenAI-compatible)                       | Catalogue                                                                                                                                                                                              |
| --------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OVHcloud AI Endpoints | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1` | [catalogue](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/); `GET /v1/models` returns id, `context_length`, `max_completion_tokens` and per-token USD pricing, but no capability flags |
| OpenAI                | `https://api.openai.com/v1`                        | [models](https://developers.openai.com/api/docs/models/gpt-5.4-mini), [pricing](https://developers.openai.com/api/docs/pricing)                                                                        |

OVH rate limit (documented, every model page): 400 requests/min per Public Cloud project and per model when authenticated; 2/min anonymous. HTTP 429 above.

## 2. OVHcloud models relevant to TABSIRA

Prices: catalogue in EUR per million tokens; the `/v1/models` endpoint returns USD per token (shown converted to USD per million). Context and max output are from `/v1/models`.

### 2.1 Vision-language and text reasoning (Qwen)

All Qwen3.5+ models on OVH are native vision-language models with reasoning; they serve both the vision stage and the text stages.

| Model id                  | Context / max output | Image input                    | Structured output                           | Reasoning     | Price in / out (EUR catalogue; USD API) |
| ------------------------- | -------------------- | ------------------------------ | ------------------------------------------- | ------------- | --------------------------------------- |
| `Qwen3.8-27B`             | 262,144 / 262,144    | yes (base64; video documented) | `json_object`, `json_schema` — **verified** | on by default | €0.40 / €2.70; $0.47 / $3.19            |
| `Qwen3.6-27B`             | 262,144 / 262,144    | yes                            | `json_object`, `json_schema` (documented)   | yes           | €0.40 / €2.70; $0.47 / $3.19            |
| `Qwen3.5-397B-A17B`       | 262,144 / 262,144    | yes                            | `json_object`, `json_schema` (documented)   | yes           | €0.60 / €3.60; $0.71 / $4.25            |
| `Qwen3.5-9B`              | 262,144 / 262,144    | yes                            | `json_object`, `json_schema` (documented)   | yes           | €0.10 / €0.15; $0.12 / $0.18            |
| `Qwen2.5-VL-72B-Instruct` | 32,768 / 32,768      | yes                            | `json_object`, `json_schema` (documented)   | no            | €0.91 / €0.91; $1.01 / $1.01            |

Other chat models on the same endpoint, not Qwen-VL, kept only as fallbacks: `Meta-Llama-3_3-70B-Instruct` (131k, $0.74/$0.74), `Mistral-Small-3.2-24B-Instruct-2506` (131k, $0.10/$0.31; listed by `/v1/models`, not found on the catalogue page, capabilities unverified), `Mistral-Nemo-Instruct-2407`, `Mistral-7B-Instruct-v0.3`, `Qwen3-Coder-30B-A3B-Instruct` (code model, not a candidate).

**Thinking cannot be switched off on OVH today.** `chat_template_kwargs: {"enable_thinking": false}` is rejected with HTTP 400 ("feature 'extra arguments' is not currently supported") — verified live. The feature request is open: [ovh/public-cloud-roadmap#1170](https://github.com/ovh/public-cloud-roadmap/issues/1170). Reasoning text arrives in `message.reasoning`, separate from `content`, and is billed as completion tokens. The benchmark must measure the latency cost of thinking and try `reasoning_effort` and prompt-level switches before a stage relies on them.

**Update, same day (benchmark):** `reasoning_effort: "none"` does switch thinking off for `Qwen3.8-27B` on OVH: the answer has no `reasoning` field and `completion_tokens_details.reasoning_tokens` is 0 (verified live, and on every call of the benchmark's `none` cells). `reasoning_effort: "low"` is accepted but changed nothing measurable on one image (397 against 384 reasoning tokens). A `/no_think` switch in the prompt is ignored (3,523 reasoning tokens). See §7.

### 2.2 Embeddings

| Model id                  | Dimensions                              | Max input | Price (EUR; USD API) | Notes                                                                                                                                                 |
| ------------------------- | --------------------------------------- | --------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bge-m3`                  | 1024 — **verified**                     | 8,192     | €0.01; $0.01         | Dense only through the API (no sparse / ColBERT output). MIT. Multilingual (Arabic is in the BGE-M3 training set; the OVH page does not name Arabic). |
| `Qwen3-Embedding-8B`      | 32–4,096 (custom dimensions documented) | 32,768    | €0.10; $0.12         | Apache 2.0. Use ≤ 2,000 dims for a pgvector `vector` HNSW index.                                                                                      |
| `bge-multilingual-gemma2` | 3,584                                   | 8,192     | €0.01; $0.01         | Gemma licence. 3,584 dims exceeds pgvector's 2,000-dim HNSW limit for `vector`; needs `halfvec` or is excluded.                                       |

### 2.3 Reranking

OVH offers **no reranking model**. Rerank candidates run in our Python service (v2 §9): `amberoad/bert-multilingual-passage-reranking-msmarco` (the reference file), `BAAI/bge-reranker-v2-m3`, or an LLM rerank through one of the chat models above.

### 2.4 Safety / guard

| Model id              | Context                    | Price       | Notes                                                                                                                                                                                                            |
| --------------------- | -------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Qwen3Guard-Gen-8B`   | 32,768 (max output 16,384) | free (beta) | Prompt and response moderation; returns `Safety: Safe/Unsafe/Controversial` plus categories (violent, illegal acts, sexual, PII, self-harm, unethical, politically sensitive, copyright). Text only. Apache 2.0. |
| `Qwen3Guard-Gen-0.6B` | 32,768                     | free (beta) | Same output format, smaller.                                                                                                                                                                                     |

## 3. OpenAI models relevant to TABSIRA

`GET /v1/models` with the project key (verified live) lists 139 models, including `gpt-5.4-mini-2026-03-17`.

| Model id                  | Context / max output     | Image input                 | Structured output                   | Reasoning effort                                   | Price per 1M (in / cached / out)              |
| ------------------------- | ------------------------ | --------------------------- | ----------------------------------- | -------------------------------------------------- | --------------------------------------------- |
| `gpt-5.4-mini-2026-03-17` | 400k / 128k              | yes — **verified**          | `json_schema` strict — **verified** | `none` (default), `low`, `medium`, `high`, `xhigh` | $0.75 / $0.075 / $4.50                        |
| `gpt-5.4-nano-2026-03-17` | 400k / 128k              | yes (documented)            | yes (documented)                    | same values                                        | $0.20 / $0.02 / $1.25                         |
| `gpt-5.4-2026-03-05`      | —                        | yes                         | yes                                 | —                                                  | $2.50 / $0.25 / $15.00 (quality ceiling only) |
| `text-embedding-3-small`  | 1536 dims — **verified** | —                           | —                                   | —                                                  | $0.02 (input)                                 |
| `text-embedding-3-large`  | 3072 dims (documented)   | —                           | —                                   | —                                                  | $0.13 (input)                                 |
| `omni-moderation-latest`  | —                        | text and image (documented) | —                                   | —                                                  | free                                          |

The cheapest current OpenAI embedding model that handles Arabic is `text-embedding-3-small` ($0.02 per 1M tokens, 1,536 dimensions, `dimensions` parameter available for shorter vectors).

The key also lists newer families (`gpt-5.5`, `gpt-5.6-*`, `gpt-6-*`). They were not examined; add them to the benchmark only if the owners ask.

## 4. What was verified live (4 October 2026)

Test image: a 64×64 PNG generated locally, left half red, right half blue (140 bytes). Prompt: name both colours; `response_format` = strict `json_schema` with two string fields.

| Call                                                                                         | Result                                             | Wall time | Tokens                         |
| -------------------------------------------------------------------------------------------- | -------------------------------------------------- | --------- | ------------------------------ |
| OVH `GET /v1/models`                                                                         | 200, 24 models                                     | 0.34 s    | —                              |
| OVH `Qwen3.8-27B` chat, image + `json_schema`, `temperature: 0`                              | 200; valid JSON; **correct** (`red`, `blue`)       | 1.37 s    | 139 in, 98 out (77 reasoning)  |
| OVH `Qwen3.8-27B` with `chat_template_kwargs`                                                | **400**, extra arguments not supported             | 0.37 s    | —                              |
| OVH `bge-m3` embedding, Arabic phrase                                                        | 200, 1,024 dims                                    | 0.43 s    | 20                             |
| OpenAI `GET /v1/models`                                                                      | 200, 139 models, `gpt-5.4-mini-2026-03-17` present | 1.28 s    | —                              |
| OpenAI `gpt-5.4-mini-2026-03-17` chat, image + strict `json_schema`, `reasoning_effort: low` | 200; valid JSON; **wrong** (`blue`, `blue`)        | 3.77 s    | 65 in, 141 out (117 reasoning) |
| OpenAI `text-embedding-3-small`, Arabic phrase                                               | 200, 1,536 dims                                    | 3.29 s    | 26                             |

Single samples. The wrong colour from `gpt-5.4-mini` is one observation on a degenerate image, not a quality verdict; the benchmark's gold scenes decide. Everything else in sections 2 and 3 is documented only.

## 5. Candidates per stage

Stage names follow v2 §22 (`vision, planner, rerank, verify, compose, chat, embedding, guard`).

| Stage     | Job                                                                                                                  | OVH candidates                                                                                              | OpenAI candidates                                                   | Local                                                                                                            |
| --------- | -------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| vision    | Scene description from the image, entities, actions, relations, pixel boxes; JSON schema; never receives the profile | `Qwen3.8-27B`, `Qwen3.6-27B`, `Qwen3.5-397B-A17B`, `Qwen3.5-9B` (speed tier)                                | `gpt-5.4-mini`, `gpt-5.4-nano` (speed tier)                         | detector in `services/vision`                                                                                    |
| planner   | Insight planner: values, actions, short retrieval queries; JSON                                                      | `Qwen3.8-27B`, `Qwen3.5-397B-A17B`, `Qwen3.5-9B`                                                            | `gpt-5.4-mini`, `gpt-5.4-nano`                                      | —                                                                                                                |
| rerank    | Order the top 20–30 Quran and hadith candidates                                                                      | LLM rerank via `Qwen3.5-9B` (no hosted reranker)                                                            | LLM rerank via `gpt-5.4-nano`                                       | `BAAI/bge-reranker-v2-m3`, `amberoad/bert-multilingual-passage-reranking-msmarco`                                |
| verify    | Evidence gate: is this candidate relevant, by id, with reason; JSON                                                  | `Qwen3.5-9B`, `Qwen3.8-27B`                                                                                 | `gpt-5.4-nano`, `gpt-5.4-mini`                                      | —                                                                                                                |
| compose   | Arabic explanation that cites evidence ids only (leak guard)                                                         | `Qwen3.8-27B`, `Qwen3.5-397B-A17B`                                                                          | `gpt-5.4-mini`                                                      | —                                                                                                                |
| chat      | Follow-up dialogue on an insight, streaming                                                                          | `Qwen3.8-27B`, `Qwen3.5-9B`                                                                                 | `gpt-5.4-mini`                                                      | —                                                                                                                |
| embedding | Arabic retrieval over 6,236 verses and the hadith books                                                              | `bge-m3`, `Qwen3-Embedding-8B` (1024 or 1536 dims)                                                          | `text-embedding-3-small`, `text-embedding-3-large` (1024/1536 dims) | existing `paraphrase-multilingual-mpnet-base-v2` verse vectors as a free baseline (see `docs/ASSET_MANIFEST.md`) |
| guard     | Image sensitivity (§6) and social moderation (posts, comments)                                                       | `Qwen3Guard-Gen-8B`, `Qwen3Guard-Gen-0.6B` (text only); image sensitivity through the vision model's schema | `omni-moderation-latest` (text and image, free)                     | —                                                                                                                |

## 6. Proposed benchmark matrix

Same gold scenes for every cell. Metrics per v2 §22: schema-valid rate (first try and after the bounded retry), human-rated scene accuracy and insight relevance, fabricated-scripture rate (leak-guard hits), latency p50/p95 per stage, cost per scan. Thinking is reported separately for every OVH Qwen cell because it cannot be turned off.

| Stage     | Primary pair (one per provider)                           | Challengers                                                                        | What decides                                                                                             |
| --------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| vision    | `Qwen3.8-27B` ↔ `gpt-5.4-mini`                            | `Qwen3.5-397B-A17B`, `Qwen3.6-27B`, `Qwen3.5-9B`, `gpt-5.4-nano`                   | entity/action accuracy, box validity after 0–1 conversion, no profile leakage, p95                       |
| planner   | `Qwen3.8-27B` ↔ `gpt-5.4-mini`                            | `Qwen3.5-397B-A17B`, `gpt-5.4-nano`                                                | retrieval recall of the queries it writes, schema validity                                               |
| rerank    | `bge-reranker-v2-m3` ↔ `amberoad/...msmarco` (both local) | LLM rerank: `Qwen3.5-9B`, `gpt-5.4-nano`                                           | nDCG@5 / MRR on gold evidence, latency (LLM rerank was ~20 s before)                                     |
| verify    | `Qwen3.5-9B` ↔ `gpt-5.4-nano`                             | `Qwen3.8-27B`, `gpt-5.4-mini`                                                      | false-accept rate on irrelevant evidence, latency                                                        |
| compose   | `Qwen3.8-27B` ↔ `gpt-5.4-mini`                            | `Qwen3.5-397B-A17B`                                                                | Arabic quality (human), leak-guard hits, id-only compliance                                              |
| chat      | `Qwen3.8-27B` ↔ `gpt-5.4-mini`                            | `Qwen3.5-9B`                                                                       | time to first token, Arabic quality                                                                      |
| embedding | `bge-m3` ↔ `text-embedding-3-small`                       | `Qwen3-Embedding-8B` @1024, `text-embedding-3-large` @1536, existing mpnet vectors | recall@20 / MRR on gold queries, separately for Quran and hadith, with and without the BM25 + RRF fusion |
| guard     | `Qwen3Guard-Gen-8B` ↔ `omni-moderation-latest`            | `Qwen3Guard-Gen-0.6B`                                                              | precision/recall on a labelled moderation set, Arabic coverage, latency                                  |

Open points for the benchmark owner:

- Thinking on OVH: measure how much of each Qwen stage's latency is reasoning tokens; if it breaks the 5–12 s target, the speed tier (`Qwen3.5-9B`) or OpenAI with `reasoning_effort: none` may win stages regardless of quality.
- `bge-multilingual-gemma2` is left out of the matrix because of its 3,584 dimensions; add it only with `halfvec`.
- Qwen3Guard is text-only; image sensitivity must come from the vision stage's own schema field (or `omni-moderation-latest` on OpenAI).

## 7. Verified while building the adapter and the benchmark (4 October 2026)

Single live calls unless a number says otherwise; the benchmark's measurements are in `docs/BENCHMARK.md`.

- **Thinking on OVH** can be switched off with `reasoning_effort: "none"` (see §2.1). With thinking on, `Qwen3.8-27B` spent 2,555 reasoning tokens on one scene analysis, which took 132 s and a second attempt; the same call without thinking took 18.7 s.
- **Qwen-VL boxes are on a 0-1000 grid.** Asked for pixel boxes of a 1344x768 image with the size stated, `Qwen3.8-27B` and `Qwen3.5-9B` answered `[556, 752, 865, 998]` for an object at pixels `[750, 575, 1165, 768]`: the 0-1000 grid. With `reasoning_effort: "low"` it mixed the two systems in one box (x on the grid, y in pixels). `gpt-5.4-mini` answered in pixels, accurately. The API therefore states the coordinate system per provider (`AI_*__BOX_COORDINATES`) and converts on the server; the benchmark measures both systems for Qwen.
- **OpenAI image moderation** (`omni-moderation-latest`): on an image input, `category_applied_input_types` lists only `sexual`, `self-harm` (three categories) and `violence` (two). It cannot see alcohol, drugs or gambling; a wine scene scored 8e-6 for violence and was not flagged. Image sensitivity therefore rests on the vision model's own `sensitive` field, with moderation as a second opinion for nudity and violence on OpenAI.
- **`max_completion_tokens`** is accepted by both providers (OVH included), so the adapter sends that one name.
- **The `openai` Python SDK** (3.24.0 on PyPI) depends on `httpx2`, a second HTTP stack beside the project's `httpx`, and retries on its own; the adapter talks to both providers with `httpx` directly so every attempt is counted in the call record.

## Sources

- OVHcloud AI Endpoints catalogue: <https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/> and model pages [`qwen-3-8-27b`](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/qwen-3-8-27b/), [`qwen-3-6-27b`](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/qwen-3-6-27b/), [`qwen-3-5-397b`](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/qwen-3-5-397b/), [`qwen-3-5-9b`](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/qwen-3-5-9b/), [`qwen-2-5-vl-72b-instruct`](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/qwen-2-5-vl-72b-instruct/), [`bge-m3`](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/bge-m3/), [`qwen3-embedding-8b`](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/qwen3-embedding-8b/), [`bge-multilingual-gemma2`](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/bge-multilingual-gemma2/), [`qwen-guard-gen-8b`](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/qwen-guard-gen-8b/)
- OVH thinking toggle request: <https://github.com/ovh/public-cloud-roadmap/issues/1170>
- OpenAI: [gpt-5.4-mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini), [gpt-5.4-nano](https://developers.openai.com/api/docs/models/gpt-5.4-nano), [pricing](https://developers.openai.com/api/docs/pricing)
- Live calls: `GET /v1/models` on both providers, 4 October 2026.
