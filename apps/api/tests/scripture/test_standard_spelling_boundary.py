"""
The readable re-spelling stays inside its module: the application imports its skeleton only.

`src.scripture.standard_spelling` can write a verse in today's spelling as text; that
text is not scripture as any approved source gives it, and must never be stored,
displayed or sent anywhere (task 05.9). Everything the application and its migrations
take from the module is `standard_skeleton`, the folded form the leak guard compares.
"""

from __future__ import annotations

import ast
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2]
MODULE = "src.scripture.standard_spelling"


def imports_of_the_module(path: Path) -> set[str]:
    """Return what `path` imports from the module (`*` for the module itself)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module == MODULE:
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module == "src.scripture":
            found.update("*" for alias in node.names if alias.name == "standard_spelling")
        elif isinstance(node, ast.Import):
            found.update("*" for alias in node.names if alias.name == MODULE)
    return found


def test_the_application_takes_only_the_skeleton_from_the_converter():
    sources = [
        path
        for folder in ("src", "alembic")
        for path in sorted((API_DIR / folder).rglob("*.py"))
        if path != API_DIR / "src" / "scripture" / "standard_spelling.py"
    ]
    imported = {str(path.relative_to(API_DIR)): imports_of_the_module(path) for path in sources}
    users = {name: names for name, names in imported.items() if names}

    assert users
    assert {name: names for name, names in users.items() if names != {"standard_skeleton"}} == {}
