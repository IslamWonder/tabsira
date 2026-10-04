from __future__ import annotations

import hashlib

import pytest

from src.pipeline.prompt import PROMPTS_DIR, load_prompt


def test_a_prompt_is_read_with_its_hash_and_version():
    prompt = load_prompt("scene_analyzer_user.v1")

    text = (PROMPTS_DIR / "scene_analyzer_user.v1.txt").read_text(encoding="utf-8")
    assert prompt.text == text
    assert prompt.sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert prompt.version == f"scene_analyzer_user.v1@{prompt.sha256[:12]}"
    assert load_prompt("scene_analyzer_user.v1") is prompt


def test_render_fills_every_placeholder_or_fails():
    prompt = load_prompt("scene_analyzer_user.v1")

    text = prompt.render(width=1344, height=768, coordinates="pixels.", detector="none.")

    assert "1344 pixels wide and 768 pixels high" in text
    assert "$" not in text
    with pytest.raises(KeyError):
        prompt.render(width=1)


def test_an_unknown_prompt_is_an_error():
    with pytest.raises(FileNotFoundError):
        load_prompt("no_such_prompt.v1")


def test_every_prompt_file_is_versioned_ascii_named_and_utf8():
    files = sorted(PROMPTS_DIR.iterdir())

    assert files
    for path in files:
        assert path.suffix == ".txt"
        assert path.stem.rsplit(".", 1)[1].startswith("v")
        assert path.name.isascii()
        assert path.name == path.name.lower()
        path.read_text(encoding="utf-8")
