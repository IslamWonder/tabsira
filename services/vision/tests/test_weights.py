from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from vision import weights
from vision.config import ModelFamily, Settings


class FakeUltralytics:
    """Just enough of the `ultralytics` module tree for the code that configures and fetches."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.settings_updates: list[dict[str, Any]] = []
        self.downloads: list[Path] = []
        self.text_models: list[tuple[str, str]] = []
        outer = self

        class FakeSettings:
            def update(self, **values: Any) -> None:
                outer.settings_updates.append(values)

        def attempt_download_asset(path: Path) -> str:
            if not path.exists():
                path.write_bytes(b"downloaded")
                outer.downloads.append(path)
            return str(path)

        def build_text_model(variant: str, device: str) -> None:
            outer.text_models.append((variant, device))

        self.utils = ModuleType("ultralytics.utils")
        self.utils.SETTINGS = FakeSettings()  # type: ignore[attr-defined]
        self.utils.WEIGHTS_DIR = None  # type: ignore[attr-defined]
        downloads = ModuleType("ultralytics.utils.downloads")
        downloads.attempt_download_asset = attempt_download_asset  # type: ignore[attr-defined]
        text_model = ModuleType("ultralytics.nn.text_model")
        text_model.build_text_model = build_text_model  # type: ignore[attr-defined]
        root = ModuleType("ultralytics")
        root.utils = self.utils  # type: ignore[attr-defined]
        for name, module in {
            "ultralytics": root,
            "ultralytics.utils": self.utils,
            "ultralytics.utils.downloads": downloads,
            "ultralytics.nn.text_model": text_model,
        }.items():
            monkeypatch.setitem(sys.modules, name, module)
        # configure_ultralytics sets these; the monkeypatch restores them afterwards.
        monkeypatch.setenv("YOLO_OFFLINE", "0")
        monkeypatch.setenv("YOLO_CONFIG_DIR", "")
        monkeypatch.setenv("YOLO_AUTOINSTALL", "True")
        monkeypatch.delenv("OMP_NUM_THREADS", raising=False)


@pytest.fixture
def ultralytics(monkeypatch: pytest.MonkeyPatch) -> FakeUltralytics:
    return FakeUltralytics(monkeypatch)


def test_encoder_ready_needs_every_file(weights_dir: Path) -> None:
    assert not weights.encoder_ready(ModelFamily.YOLOE, weights_dir)
    assert not weights.encoder_ready(ModelFamily.YOLO_WORLD, weights_dir)

    (weights_dir / "mobileclip_blt.ts").write_bytes(b"x")
    (weights_dir / "clip").mkdir()
    (weights_dir / "clip" / "ViT-B-32.pt").write_bytes(b"x")

    assert weights.encoder_ready(ModelFamily.YOLOE, weights_dir)
    assert weights.encoder_ready(ModelFamily.YOLO_WORLD, weights_dir)


def test_configure_ultralytics_isolates_its_settings(
    ultralytics: FakeUltralytics, weights_dir: Path
) -> None:
    weights.configure_ultralytics(weights_dir)

    assert (weights_dir / ".config").is_dir()
    assert os.environ["YOLO_CONFIG_DIR"] == str(weights_dir / ".config")
    assert os.environ["YOLO_OFFLINE"] == "1"
    assert os.environ["YOLO_AUTOINSTALL"] == "False"
    assert 1 <= int(os.environ["OMP_NUM_THREADS"]) <= 4
    assert ultralytics.settings_updates == [{"weights_dir": str(weights_dir), "sync": False}]
    assert weights_dir == ultralytics.utils.WEIGHTS_DIR


def test_configure_ultralytics_leaves_a_thread_count_the_operator_chose(
    ultralytics: FakeUltralytics, weights_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "2")

    weights.configure_ultralytics(weights_dir)

    assert os.environ["OMP_NUM_THREADS"] == "2"


def test_fetch_weights_downloads_the_yoloe_checkpoint_and_encoder(
    ultralytics: FakeUltralytics, settings: Settings
) -> None:
    paths = weights.fetch_weights(settings)

    folder = settings.vision_weights_dir
    assert paths == [folder / "yoloe-11s-seg.pt", folder / "mobileclip_blt.ts"]
    assert ultralytics.downloads == paths
    assert ultralytics.text_models == []


def test_fetch_weights_is_idempotent(ultralytics: FakeUltralytics, settings: Settings) -> None:
    first = weights.fetch_weights(settings)
    ultralytics.downloads.clear()

    second = weights.fetch_weights(settings)

    assert second == first
    assert ultralytics.downloads == []


def test_fetch_weights_creates_the_weights_directory(
    ultralytics: FakeUltralytics, tmp_path: Path
) -> None:
    target = tmp_path / "a" / "weights"
    settings = Settings(_env_file=None, vision_weights_dir=target)

    weights.fetch_weights(settings)

    assert (target / "yoloe-11s-seg.pt").is_file()


def test_fetch_weights_for_yolo_world_builds_the_clip_encoder(
    ultralytics: FakeUltralytics, weights_dir: Path
) -> None:
    settings = Settings(
        _env_file=None, vision_weights_dir=weights_dir, detector_model="yolov8s-worldv2.pt"
    )

    paths = weights.fetch_weights(settings)

    assert paths == [weights_dir / "yolov8s-worldv2.pt", weights_dir / "clip" / "ViT-B-32.pt"]
    assert ultralytics.downloads == [weights_dir / "yolov8s-worldv2.pt"]
    assert ultralytics.text_models == [("clip:ViT-B/32", "cpu")]


def test_fetch_weights_for_yolo_world_skips_an_encoder_that_is_there(
    ultralytics: FakeUltralytics, weights_dir: Path
) -> None:
    (weights_dir / "clip").mkdir()
    (weights_dir / "clip" / "ViT-B-32.pt").write_bytes(b"x")
    settings = Settings(
        _env_file=None, vision_weights_dir=weights_dir, detector_model="yolov8s-worldv2.pt"
    )

    weights.fetch_weights(settings)

    assert ultralytics.text_models == []


def test_main_reports_what_it_fetched(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    file = tmp_path / "yoloe-11s-seg.pt"
    file.write_bytes(b"x" * 2_000_000)
    monkeypatch.setattr(weights, "Settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(weights, "fetch_weights", lambda _settings: [file])

    ranker = tmp_path / "model.safetensors"
    ranker.write_bytes(b"x" * 3_000_000)
    monkeypatch.setattr(weights, "fetch_reranker", lambda _settings: [ranker])

    with caplog.at_level(logging.INFO, logger="vision.weights"):
        weights.main()

    assert "yoloe-11s-seg.pt (2.0 MB)" in caplog.text
    assert "model.safetensors (3.0 MB)" in caplog.text


class FakeHub:
    """The two calls of `huggingface_hub` that fetch_reranker makes."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, files: list[str]) -> None:
        self.files = files
        self.downloads: list[tuple[str, str, list[str]]] = []
        hub = ModuleType("huggingface_hub")
        hub.list_repo_files = lambda repo: list(self.files)  # type: ignore[attr-defined]
        hub.snapshot_download = self.snapshot_download  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    def snapshot_download(self, repo: str, *, local_dir: str, allow_patterns: list[str]) -> str:
        self.downloads.append((repo, local_dir, allow_patterns))
        return local_dir


def test_fetch_reranker_downloads_the_weights_and_the_tokenizer_only(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    files = ["README.md", "config.json", "tokenizer.json", "model.safetensors", "pytorch_model.bin"]
    hub = FakeHub(monkeypatch, files)

    paths = weights.fetch_reranker(settings)

    directory = settings.vision_weights_dir / "rerankers" / "BAAI--bge-reranker-v2-m3"
    wanted = ["config.json", "tokenizer.json", "model.safetensors"]
    assert hub.downloads == [("BAAI/bge-reranker-v2-m3", str(directory), wanted)]
    assert paths == [directory / name for name in wanted]


def test_fetch_reranker_refuses_a_repository_without_weights(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    FakeHub(monkeypatch, ["config.json"])

    with pytest.raises(FileNotFoundError, match=r"neither model\.safetensors"):
        weights.fetch_reranker(settings)
