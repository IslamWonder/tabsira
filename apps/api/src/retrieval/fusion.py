"""
Reciprocal Rank Fusion: one ranking from several, without comparing their scores.

Vector similarity, full-text weights and concept matches live on different
scales, so only ranks are combined: a text at rank r of a list earns
weight / (k + r), summed over every list that holds it (Cormack, Clarke and
Buettcher, SIGIR 2009; k = 60 is their value). A text found by several queries
and several methods rises; the same text found twice in one list counts once,
and the result holds each text once.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.retrieval.lexical import Hit

RRF_K = 60


@dataclass(frozen=True, slots=True)
class FusedHit:
    """A text after fusion: its key, its fused score, and its rank in each list that held it."""

    key: int
    score: float
    ranks: tuple[tuple[str, int], ...]

    def best_rank(self) -> int:
        return min(rank for _, rank in self.ranks)


def fuse(
    lists: Mapping[str, Sequence[Hit]],
    *,
    weights: Mapping[str, float] | None = None,
    k: int = RRF_K,
) -> list[FusedHit]:
    """Fuse named rankings; a list's weight is looked up by the part of its name before `:`."""
    scores: dict[int, float] = defaultdict(float)
    ranks: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for name, hits in lists.items():
        weight = (weights or {}).get(name.split(":", 1)[0], 1.0)
        seen: set[int] = set()
        for rank, hit in enumerate(hits, start=1):
            if hit.key in seen:
                continue
            seen.add(hit.key)
            scores[hit.key] += weight / (k + rank)
            ranks[hit.key].append((name, rank))
    ordered = sorted(scores, key=lambda key: (-scores[key], key))
    return [FusedHit(key, scores[key], tuple(ranks[key])) for key in ordered]
