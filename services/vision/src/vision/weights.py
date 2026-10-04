"""
Where the weights live, how Ultralytics is told, and how they are fetched.

A checkpoint (`yoloe-11s-seg.pt`) is not enough on its own: an open vocabulary
needs a text encoder, a second file of 340 to 600 MB that Ultralytics would
download on the first request. Here both are fetched ahead of time by
`scripts/fetch-weights.sh`, with the reranker's model from the Hugging Face
hub (its weights, configuration and tokenizer files only), and the service
never downloads anything.
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Any

from vision.config import ModelFamily, Settings, family_of
from vision.reranker import model_directory

logger = logging.getLogger(__name__)

# Text encoder of each family, relative to the weights directory.
ENCODER_FILES: dict[ModelFamily, tuple[str, ...]] = {
    ModelFamily.YOLOE: ("mobileclip_blt.ts",),
    ModelFamily.YOLO_WORLD: ("clip/ViT-B-32.pt",),
}


def encoder_ready(family: ModelFamily, weights_dir: Path) -> bool:
    """Tell whether the text encoder of this family is on disk."""
    return all((weights_dir / name).is_file() for name in ENCODER_FILES[family])


def configure_ultralytics(weights_dir: Path) -> None:
    """
    Point Ultralytics at our weights directory and keep it quiet.

    Must run before the first model is built. Ultralytics keeps a settings file in
    the user's home and, left alone, would share it with every other project, look
    for weights in the repository root, probe the network at import and send usage
    analytics. The service keeps its own copy inside the weights directory instead.
    """
    config_dir = weights_dir / ".config"
    config_dir.mkdir(parents=True, exist_ok=True)  # Ultralytics ignores a directory that is missing
    os.environ["YOLO_OFFLINE"] = "1"
    os.environ["YOLO_AUTOINSTALL"] = "False"  # a service never pip-installs while it runs
    os.environ["YOLO_CONFIG_DIR"] = str(config_dir)
    # Ultralytics sets one thread, which suits training. On an 8-core CPU four threads
    # halved the start-up encoding and cut inference from about 190 to 110 ms.
    os.environ.setdefault("OMP_NUM_THREADS", str(min(4, os.cpu_count() or 1)))

    utils: Any = importlib.import_module("ultralytics.utils")
    utils.SETTINGS.update(weights_dir=str(weights_dir), sync=False)
    # Read once at import by the CLIP text encoder, so the setting alone is too late.
    utils.WEIGHTS_DIR = weights_dir


def fetch_weights(settings: Settings) -> list[Path]:
    """Download the checkpoint and its text encoder into the weights directory; skip what exists."""
    weights_dir = settings.vision_weights_dir
    weights_dir.mkdir(parents=True, exist_ok=True)
    configure_ultralytics(weights_dir)

    attempt_download_asset = importlib.import_module(
        "ultralytics.utils.downloads"
    ).attempt_download_asset

    family = family_of(settings.detector_model)
    checkpoint = weights_dir / settings.detector_model
    attempt_download_asset(checkpoint)

    encoder = [weights_dir / name for name in ENCODER_FILES[family]]
    if not encoder_ready(family, weights_dir):
        if family is ModelFamily.YOLOE:
            attempt_download_asset(encoder[0])
        else:
            text_model = importlib.import_module("ultralytics.nn.text_model")
            text_model.build_text_model("clip:ViT-B/32", "cpu")  # downloads into weights/clip
    return [checkpoint, *encoder]


# A reranker's weights, safetensors preferred; and the files its tokenizer may need.
RERANKER_WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")
RERANKER_SIDE_FILES = (
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
    "vocab.txt",
)


def fetch_reranker(settings: Settings) -> list[Path]:
    """Download the reranker's weights and tokenizer into weights/rerankers/; skip what exists."""
    hub: Any = importlib.import_module("huggingface_hub")
    repo = settings.vision_reranker_model
    files = set(hub.list_repo_files(repo))
    weights = [name for name in RERANKER_WEIGHT_FILES if name in files][:1]
    if not weights:
        message = f"{repo} has neither model.safetensors nor pytorch_model.bin"
        raise FileNotFoundError(message)
    wanted = [name for name in RERANKER_SIDE_FILES if name in files] + weights
    directory = model_directory(settings.vision_weights_dir, repo)
    hub.snapshot_download(repo, local_dir=str(directory), allow_patterns=wanted)
    return [directory / name for name in wanted]


def main() -> None:
    """Command line entry point of `scripts/fetch-weights.sh`."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings()
    for path in [*fetch_weights(settings), *fetch_reranker(settings)]:
        logger.info("%s (%.1f MB)", path, path.stat().st_size / 1_000_000)


if __name__ == "__main__":
    main()
