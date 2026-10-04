"""The one error family of the scripture store, so a command can report any of them plainly."""

from __future__ import annotations


class ScriptureError(RuntimeError):
    """A source, a file or a write of the scripture store was refused; the message says which."""
