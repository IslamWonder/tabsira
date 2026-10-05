"""
Versioned prompt files.

A prompt lives in `prompts/<name>.v<N>.txt`. Changing what a prompt says means
a new file with the next version, so a recorded result always names the exact
text that produced it (name and content hash).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).with_name("prompts")


@dataclass(frozen=True)
class Prompt:
    """The text of one prompt file and its identity."""

    name: str
    text: str
    sha256: str

    @property
    def version(self) -> str:
        """`name@hash`: what a result records about the prompt that produced it."""
        return f"{self.name}@{self.sha256[:12]}"

    def render(self, **values: object) -> str:
        """Fill the `$placeholders`; a missing value is an error, not an empty string."""
        return Template(self.text).substitute({key: str(value) for key, value in values.items()})


@lru_cache(maxsize=32)
def load_prompt(name: str) -> Prompt:
    """Read `prompts/<name>.txt`, e.g. `load_prompt("scene_analyzer_system.v2")`."""
    path = PROMPTS_DIR / f"{name}.txt"
    text = path.read_text(encoding="utf-8")
    return Prompt(name=name, text=text, sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
