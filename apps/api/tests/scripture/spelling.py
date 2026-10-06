"""
A stored Uthmani verse as a writer could spell it today, built from the stored text.

Tests need a verse as a model would write it. Typing one by hand is not allowed
(a test never carries hand-typed scripture), so it is derived from the stored
text: `standard` is the application's own converter
(`src.scripture.standard_spelling`), and `variant` makes the converter's
choices at random instead (a dagger alef written or not, an open teh kept or
made marbuta, a final yeh doubled, the vocative written apart or joined), to
sweep a sample of the store with spellings the converter itself would not give.
"""

from __future__ import annotations

import random

from src.scripture.standard_spelling import standard, standard_word, vocative

__all__ = ["standard", "variant"]


def _word(word: str, rng: random.Random) -> str:
    return standard_word(
        word,
        keep_alef=rng.random() < 0.5,
        open_teh=rng.random() < 0.5,
        long_yeh=rng.random() < 0.3,
    )


def variant(text: str, rng: random.Random) -> str:
    """Return `text` in one of the spellings a writer could use, chosen by `rng`."""
    words: list[str] = []
    for word in text.split():
        split = vocative(word)
        if split is None:
            words.append(_word(word, rng))
            continue
        particle, called = split
        apart = rng.random() < 0.8
        words.extend([particle, _word(called, rng)] if apart else [particle + _word(called, rng)])
    return " ".join(words)
