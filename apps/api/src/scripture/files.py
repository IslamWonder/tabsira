"""Downloaded source files: checked against a known SHA-256 and written whole or not at all."""

from __future__ import annotations

import hashlib
from pathlib import Path


class SourceFileError(RuntimeError):
    """A source file is missing, or its bytes are not the ones expected."""


def bytes_sha256(data: bytes) -> str:
    """Return the SHA-256 of `data` in lower-case hex."""
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 of the file at `path`, read in blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_verified(path: Path, sha256: str) -> bool:
    """Return whether `path` exists and its bytes hash to `sha256`."""
    return path.is_file() and file_sha256(path) == sha256


def require_verified(path: Path, sha256: str) -> Path:
    """Return `path` when its bytes hash to `sha256`; raise naming the file otherwise."""
    if not path.is_file():
        message = f"{path} is missing"
        raise SourceFileError(message)
    actual = file_sha256(path)
    if actual != sha256:
        message = f"{path} has sha256 {actual}, expected {sha256}"
        raise SourceFileError(message)
    return path


def check_bytes(data: bytes, sha256: str, label: str) -> bytes:
    """Return `data` when it hashes to `sha256`; raise naming `label` otherwise."""
    actual = bytes_sha256(data)
    if actual != sha256:
        message = f"{label} has sha256 {actual}, expected {sha256}"
        raise SourceFileError(message)
    return data


def write_atomically(path: Path, data: bytes) -> Path:
    """Write `data` to `path` through a temporary file, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    partial.write_bytes(data)
    partial.replace(path)
    return path
