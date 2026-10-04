"""Test support for the ontology: small workbooks, the real one, and a database that holds it."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from openpyxl import Workbook
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.models import OntologyEntity
from src.services.ontology_import import (
    HEADERS,
    SHEET_NAME,
    ParsedOntology,
    load_ontology,
    read_workbook,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
API_DIR = REPO_ROOT / "apps" / "api"
REAL_WORKBOOK = REPO_ROOT / "data" / "world-ontology.xlsx"
REAL_JSON = REPO_ROOT / "data" / "ontology" / "world-ontology.json"
HEADER_ORDER = list(HEADERS.values())


def good_row(number: int, **cells: Any) -> list[Any]:
    """One valid data row, in the order of the columns; `cells` overrides a column by field name."""
    values: dict[str, Any] = {
        "label_ar": f"شيء {number}",
        "related_objects": f"شيء {number}، رابط",
        "actions_and_uses": "نظر، استعمال",
        "contextual_concepts": "تأمل، شكر",
        "special_constraint": None,
        "domain": "مجال تجريبي",
        "id": f"E{number:03d}",
    }
    values.update(cells)
    return [values[name] for name in HEADERS]


def workbook_bytes(
    rows: Sequence[Sequence[Any]],
    *,
    sheet: str = SHEET_NAME,
    title_rows: int = 2,
    headers: Sequence[Any] | None = None,
    extra_sheets: Sequence[str] = (),
) -> bytes:
    """Build an .xlsx in memory: title rows, a blank row, the header, then `rows`."""
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = sheet
    for index in range(title_rows):
        worksheet.append([f"سطر عنوان {index}"])
    if title_rows:
        worksheet.append([])
    worksheet.append(list(HEADER_ORDER if headers is None else headers))
    for row in rows:
        worksheet.append(list(row))
    for name in extra_sheets:
        workbook.create_sheet(name)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@cache
def parsed_real_ontology() -> ParsedOntology:
    """The real workbook, parsed once for the whole run."""
    return read_workbook(REAL_WORKBOOK)


@pytest.fixture(scope="session")
def real_ontology() -> ParsedOntology:
    return parsed_real_ontology()


@pytest_asyncio.fixture
async def ontology(db_session: AsyncSession) -> ParsedOntology:
    """The 1000 real entities, loaded into the test session's transaction."""
    parsed = parsed_real_ontology()
    await load_ontology(db_session, parsed)
    return parsed


@pytest_asyncio.fixture(scope="module")
async def committed_ontology(engine: AsyncEngine) -> AsyncIterator[ParsedOntology]:
    """
    The 1000 real entities, committed once for a whole test module and removed after it.

    Loading takes a third of a second, which adds up over dozens of resolver tests; the
    tests themselves still run in rolled-back sessions on top of these rows.
    """
    parsed = parsed_real_ontology()
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await load_ontology(session, parsed)
    yield parsed
    async with factory() as session, session.begin():
        await session.execute(delete(OntologyEntity))


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """
    A session factory whose commits are savepoints of one outer transaction.

    Code that opens and commits its own session (the command-line importers) can be
    run against the test database without leaving a row behind.
    """
    async with engine.connect() as connection:
        outer = await connection.begin()
        yield async_sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        await outer.rollback()
