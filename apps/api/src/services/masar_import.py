"""
Load a learning path file into `app.learning_*`.

A path version is published once: its file is hashed, and importing the same file
again changes nothing. A new release is a new version (a new `path_version` and a
new file), added next to the others without a change to the code. Replacing a
published version is possible only on purpose (`replace=True`), and not while a
learner has state for a unit the new file drops.

At most one version is active. By default a first version becomes active and a later
one waits to be activated; `activate=True` switches the active version to this one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import batched
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.learning import LearningDomain, LearningPathVersion, LearningUnit
from src.schemas.learning_path import LearningPathFile

ROWS_PER_INSERT = 250


class PathVersionConflictError(Exception):
    """The version exists with other content, or learners still depend on what a replacement drops."""


class LoadStatus(StrEnum):
    """What a load did to the version."""

    CREATED = "created"
    UNCHANGED = "unchanged"
    REPLACED = "replaced"


@dataclass(frozen=True, slots=True)
class PathLoadResult:
    """The outcome of a load."""

    path_version: str
    status: LoadStatus
    domains: int
    units: int
    active: bool


def _version_values(path: LearningPathFile, source_file: str, source_sha256: str) -> dict[str, Any]:
    dumped = path.model_dump(mode="json")
    return {
        "path_version": path.path_version,
        "title": path.title,
        "version": path.version,
        "released_on": path.released_on,
        "description": path.description,
        "source_file": source_file,
        "source_sha256": source_sha256,
        "domain_count": len(path.domains),
        "unit_count": len(path.units),
        "depths": dumped["depths"],
        "coverage": dumped["coverage"],
        "imported_at": func.now(),
    }


def _domain_rows(path: LearningPathFile) -> list[dict[str, Any]]:
    return [
        {
            "path_version": path.path_version,
            "id": domain.id,
            "position": domain.order,
            "title": domain.title,
            "function": domain.function,
            "goal": domain.goal,
            "concepts": list(domain.concepts),
        }
        for domain in path.domains
    ]


def _unit_rows(path: LearningPathFile) -> list[dict[str, Any]]:
    return [
        {
            "path_version": path.path_version,
            "id": unit.id,
            "domain_id": unit.domain,
            "position": unit.order,
            "title": unit.title,
            "objectives": list(unit.objectives),
            "prerequisites": list(unit.prerequisites),
            "depths": list(unit.depths),
            "concepts": list(unit.concepts),
            "evidence_refs": list(unit.evidence_refs),
            "source_anchors": list(unit.source_anchors),
        }
        for unit in path.units
    ]


async def _upsert(
    session: AsyncSession, model: Any, rows: list[dict[str, Any]], keys: list[str]
) -> None:
    for batch in batched(rows, ROWS_PER_INSERT):
        insertion = insert(model).values(list(batch))
        replaced = {name: insertion.excluded[name] for name in batch[0] if name not in keys}
        await session.execute(insertion.on_conflict_do_update(index_elements=keys, set_=replaced))


async def _write(
    session: AsyncSession, path: LearningPathFile, version: dict[str, Any], *, replacing: bool
) -> None:
    """Write the version, its domains and its units; when replacing, drop what the file no longer has."""
    await _upsert(session, LearningPathVersion, [version], ["path_version"])
    await _upsert(session, LearningDomain, _domain_rows(path), ["path_version", "id"])
    if replacing:
        # Units before domains: a unit belongs to its domain.
        await session.execute(
            delete(LearningUnit).where(
                LearningUnit.path_version == path.path_version,
                LearningUnit.id.not_in([unit.id for unit in path.units]),
            )
        )
        await session.execute(
            delete(LearningDomain).where(
                LearningDomain.path_version == path.path_version,
                LearningDomain.id.not_in([domain.id for domain in path.domains]),
            )
        )
    await _upsert(session, LearningUnit, _unit_rows(path), ["path_version", "id"])


async def _activate(session: AsyncSession, path_version: str, activate: bool | None) -> bool:
    """Apply the activation rule; return whether `path_version` is the active version."""
    current = await session.scalar(
        select(LearningPathVersion.path_version).where(LearningPathVersion.is_active.is_(True))
    )
    if activate is True or (activate is None and current is None):
        # The one active version is switched, never two at once.
        await session.execute(
            update(LearningPathVersion)
            .where(LearningPathVersion.is_active.is_(True))
            .values(is_active=False)
        )
        await session.execute(
            update(LearningPathVersion)
            .where(LearningPathVersion.path_version == path_version)
            .values(is_active=True)
        )
        return True
    return current == path_version


async def import_path(
    session: AsyncSession,
    path: LearningPathFile,
    *,
    source_file: str,
    source_sha256: str,
    activate: bool | None = None,
    replace: bool = False,
) -> PathLoadResult:
    """
    Load `path`, a validated file whose text has the hash `source_sha256`.

    The same hash for the same version changes nothing; another hash for an existing
    version raises `PathVersionConflictError` unless `replace` is set. The caller
    owns the transaction and has already validated the file.
    """
    existing = await session.get(LearningPathVersion, path.path_version)
    if existing is not None and existing.source_sha256 == source_sha256:
        status = LoadStatus.UNCHANGED
    elif existing is not None and not replace:
        message = (
            f"The version {path.path_version} is already published with other content. "
            "A published version does not change: publish a new path_version, or replace it on purpose."
        )
        raise PathVersionConflictError(message)
    else:
        status = LoadStatus.CREATED if existing is None else LoadStatus.REPLACED
        version = _version_values(path, source_file, source_sha256)
        try:
            async with session.begin_nested():
                await _write(session, path, version, replacing=existing is not None)
        except IntegrityError:
            message = (
                f"Learners have state for units that the new {path.path_version} no longer has: "
                "it cannot be replaced, publish a new path_version."
            )
            raise PathVersionConflictError(message) from None
    active = await _activate(session, path.path_version, activate)
    return PathLoadResult(path.path_version, status, len(path.domains), len(path.units), active)
