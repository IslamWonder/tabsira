"""Where the importers look for their files when no directory is given on the command line."""

from __future__ import annotations

from pathlib import Path

# apps/api/src/scripture/paths.py -> the repository root, four levels up.
REPO_ROOT = Path(__file__).resolve().parents[4]
# Downloads, checked against their SHA-256 (ignored by git).
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "cache"
# The project's own corpora, too large for git, copied here by hand (ignored by git).
DEFAULT_CORPUS_DIR = REPO_ROOT / "data" / "corpus"
