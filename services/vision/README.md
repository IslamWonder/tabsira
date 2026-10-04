# TABSIRA vision

The object detector of TABSIRA. A small FastAPI service that finds the things in a photo with an open vocabulary (Ultralytics YOLOE, or YOLO-World as the alternative) and returns them with English and Arabic labels and boxes as ratios of the image. It also serves the cross-encoder that reranks the API's evidence candidates (`POST /rerank`), since it already carries torch.

It is reached only over HTTP, by the API, behind the `DETECTOR` interface (decision 5 in `docs/spec/DECISIONS.md`), so it can be swapped for another detector. It binds to `127.0.0.1`, has no authentication and no CORS: the API is its only caller.

## Run it

```bash
cd services/vision
uv sync                           # or `make install` from the root
bash scripts/fetch-weights.sh     # about 630 MB, once; later runs download nothing
uv run vision                     # http://127.0.0.1:8100, model loaded at start-up
```

- Development with reload: `uv run uvicorn vision.main:create_app --factory --reload`.
- Production, one worker (each worker holds the model in memory): `uv run gunicorn "vision.main:create_app()" -k uvicorn_worker.UvicornWorker -w 1 -b 127.0.0.1:8100 --timeout 120`.
- Another checkpoint: `bash scripts/fetch-weights.sh yolov8s-worldv2.pt`, then run with `DETECTOR_MODEL=yolov8s-worldv2.pt`.

The model and its vocabulary are loaded at start-up (`VISION_WARMUP=true`, about 6 to 12 s on a laptop CPU, mostly the text encoder turning the 114 default labels into classes). With `VISION_WARMUP=false` the first request pays for that instead.

## Endpoints

### `GET /health`

```json
{
  "ok": true,
  "detector": "yoloe",
  "model": "yoloe-11s-seg",
  "device": "cpu",
  "modelLoaded": true,
  "vocabularySize": 114,
  "vocabularyMode": "open",
  "error": null,
  "reranker": "BAAI/bge-reranker-v2-m3",
  "rerankerLoaded": false,
  "rerankerError": null
}
```

`reranker*` describe the cross-encoder of `POST /rerank` and do not change `ok`, which speaks for the detector.

`ok` is false, with `error` filled, when the weights or the text encoder are missing or damaged. `vocabularyMode` is `unloaded` before the first detection, `open` when the requested vocabulary is in use, and `coco` when the text encoder is unavailable and a YOLO-World checkpoint falls back to the 80 COCO classes it ships with (the `vocabulary` of a request is then ignored). A YOLOE checkpoint has no classes of its own, so without its encoder it answers 503.

### `POST /detect`

Multipart form: `image` (JPEG, PNG or WebP), `vocabulary` (comma-separated English labels, at most 500, default the built-in 114), `conf` (0 to 1, default 0.2), `max_detections` (1 to 300, default 20).

```bash
curl -s -F image=@photo.jpg -F vocabulary="olive,tree,rain" -F conf=0.2 http://127.0.0.1:8100/detect
```

### `POST /detect-json`

The same, as JSON: `{"imageBase64": "...", "vocabulary": ["olive", "tree"], "conf": 0.2, "maxDetections": 20}`. `imageBase64` is bare base64 or a `data:image/...;base64,` URL; `vocabulary` may also be a comma-separated string.

### Response

```json
{
  "detections": [
    {
      "id": "d1",
      "label": "flower",
      "labelArabic": "زهرة",
      "confidence": 0.7071,
      "bbox": { "x": 0.0234, "y": 0.2539, "width": 0.9199, "height": 0.5863 }
    }
  ],
  "width": 768,
  "height": 1344,
  "model": "yoloe-11s-seg",
  "ms": 131,
  "vocabularyMode": "open"
}
```

- `bbox` is in ratios (0 to 1) of the image that was received, after its EXIF orientation is applied, which is also what `width` and `height` describe. `x` and `y` are the top-left corner. A box outside the image is dropped and one that crosses the border is clamped.
- Detections are sorted by confidence; `id` is `d1`, `d2`, and so on.
- `labelArabic` is `null` for a label that is not in `src/vision/vocabulary.py`: the service never guesses a translation.
- `ms` is the time in the detector (inference, plus loading or encoding a new vocabulary when that was needed), not the upload or the decoding.

### `POST /rerank`

JSON: `{"query": "إحياء الأرض بالمطر", "passages": ["...", "..."]}`, 1 to 64 passages of at most 4,000 characters, a query of at most 1,000. The answer has one relevance score from 0 to 1 per passage, in the order sent: `{"scores": [0.91, 0.02], "model": "BAAI/bge-reranker-v2-m3", "ms": 840}`. The model reads the query and each passage together (a cross-encoder); a pair longer than `VISION_RERANKER_MAX_LENGTH` tokens is cut on the passage side. A model with one logit is read through a sigmoid, one with two (the msmarco passage rerankers) as the probability of the relevant class. Without its weights it answers 503 `reranker_unavailable`, and the API keeps its own order.

### Errors

Every error is `{"error": code, "detail": message}`.

| Status | `error`                                          | When                                                                                                             |
| ------ | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| 400    | `empty_image`, `invalid_base64`, `invalid_image` | no bytes, bad base64, a JPEG, PNG or WebP that will not decode                                                   |
| 413    | `image_too_large`                                | over `VISION_MAX_IMAGE_BYTES`, over `VISION_MAX_IMAGE_PIXELS`, a decompression bomb, or a body too large to read |
| 415    | `unsupported_media_type`                         | the bytes are not a JPEG, PNG or WebP image                                                                      |
| 422    | `invalid_request`, `vocabulary_too_large`        | a field is missing or out of range, more than 500 labels                                                         |
| 503    | `detector_unavailable`, `reranker_unavailable`   | weights or text encoder missing or damaged                                                                       |
| 500    | `internal_error`                                 | anything else; the details go to the log, not the response                                                       |

## Configuration

Read from the environment and from the root `.env` (see `.env.example`). The typed settings are in `src/vision/config.py`.

| Key                       | Default                   | Meaning                                                                                   |
| ------------------------- | ------------------------- | ----------------------------------------------------------------------------------------- |
| `VISION_HOST`             | `127.0.0.1`               | address to bind; keep it loopback                                                         |
| `VISION_PORT`             | `8100`                    | port                                                                                      |
| `VISION_WEIGHTS_DIR`      | `services/vision/weights` | checkpoint and text encoder (git-ignored)                                                 |
| `VISION_MAX_IMAGE_BYTES`  | `15728640` (15 MB)        | largest upload                                                                            |
| `VISION_MAX_IMAGE_PIXELS` | `40000000`                | largest decoded image, checked from the header before decoding                            |
| `VISION_WARMUP`           | `true`                    | load the model and the default vocabulary at start-up                                     |
| `DETECTOR_MODEL`          | `yoloe-11s-seg.pt`        | `yoloe-11s-seg.pt` or `yolov8s-worldv2.pt` (any `yoloe-*` or `yolov8*-world*` checkpoint) |
| `DETECTOR_DEVICE`         | `cpu`                     | `cpu`, `mps` or `cuda`                                                                    |
| `DETECTOR_CONF`           | `0.2`                     | confidence threshold when a request does not give one                                     |
| `DETECTOR_MAX_DETECTIONS` | `20`                      | detections kept when a request does not give a limit                                      |

| Key                          | Default                   | Meaning                                                                               |
| ---------------------------- | ------------------------- | ------------------------------------------------------------------------------------- |
| `VISION_RERANKER_MODEL`      | `BAAI/bge-reranker-v2-m3` | the cross-encoder of `POST /rerank`, a Hugging Face id, chosen by `docs/BENCHMARK.md` |
| `VISION_RERANKER_MAX_LENGTH` | `256`                     | tokens of one query and passage pair (32 to 512)                                      |
| `VISION_RERANKER_WARMUP`     | `false`                   | load the reranker at start-up (about 2.3 GB of memory for bge-reranker-v2-m3 in fp32) |

`OMP_NUM_THREADS` is honoured. Ultralytics would otherwise run on one thread; the service picks `min(4, cores)`, which on an 8-core CPU halved the start-up encoding and cut inference from about 190 ms to about 110 ms.

## Weights and the text encoder

An open vocabulary needs two files: the checkpoint and a text encoder that turns the labels into classes (MobileCLIP, 600 MB, for YOLOE; CLIP ViT-B/32, 354 MB, for YOLO-World). `scripts/fetch-weights.sh` downloads both into `weights/`, skipping what is there. The service itself never downloads anything: Ultralytics is run offline, with its own settings file kept inside `weights/.config`, no usage analytics and no run-time package installs.

The reranker's weights, configuration and tokenizer files (2.3 GB for `BAAI/bge-reranker-v2-m3`) are fetched by the same script from the Hugging Face hub into `weights/rerankers/<org>--<name>/`; Transformers then runs offline.

Its last vocabulary stays encoded, so repeated requests with the same labels cost only the inference; a different vocabulary is encoded again (a few seconds for 114 labels on a CPU). Requests are served one at a time, as Ultralytics predictors are not thread-safe.

## Privacy

A photo is decoded in memory and never written to disk or logged: an upload is held in memory (Starlette would spool it to a temporary file beyond 1 MB, so the service raises that limit to the size it accepts). The log has the size of the work, not its content.

## Tests

```bash
uv run pytest --cov     # 100 % line and branch coverage; the Ultralytics model is faked, no weights, no network
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## Licence

Ultralytics is AGPL-3.0, so this service is too. The full text is in [`LICENSE`](LICENSE). The licence of the rest of the repository is pending the owners' choice.
