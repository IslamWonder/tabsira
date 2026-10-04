"""
The notice about where photos are kept (decision 44).

Production requires S3 and refuses to start without a usable bucket (`src/storage/probe.py`).
Development and test fall back to the local disk, and say so at start, so nobody takes the
disk for the real thing.
"""

from __future__ import annotations

import logging

from src.config import Settings

log = logging.getLogger("tabsira.storage")

_announced: set[str] = set()


def storage_notice(settings: Settings) -> str | None:
    """Return the text to say about the local store; None when photos go to S3."""
    if settings.resolved_storage_backend != "local":
        return None
    return f"No S3 bucket: photos go to {settings.local_media_path}; production requires S3."


def announce_storage(settings: Settings) -> None:
    """Log the notice once per process, however many times the application is built."""
    text = storage_notice(settings)
    if text is None or text in _announced:
        return
    _announced.add(text)
    log.warning(text)
