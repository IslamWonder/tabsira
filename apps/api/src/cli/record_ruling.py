"""
Record a dorar.net ruling for a hadith, or list the hadiths waiting for one (decision 18).

For editors, until the admin area exists:

    uv run python -m src.cli.record_ruling queue [--limit N]
    uv run python -m src.cli.record_ruling record COLLECTION NUMBER
        (--ruling TEXT | --ruling-file PATH) --scholar NAME --book TITLE --page PAGE
        --url https://dorar.net/h/... --editor NAME
        --classification {صحيح,حسن,ضعيف,موضوع,مختلف_فيه}

Open dorar.net in a browser (the queue prints a search link for each hadith),
then copy the ruling exactly as dorar gives it. A long ruling is safest in a
UTF-8 file passed with --ruling-file (one final newline is dropped, nothing
else). Rulings are never edited: a new one is recorded instead, and the latest
one is in force. Exit 0 on success, 1 when the hadith or the ruling is refused.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database import dispose_engine, get_sessionmaker
from src.models import HadithClassification
from src.scripture.errors import ScriptureError
from src.scripture.links import dorar_search_url
from src.scripture.rulings import (
    RulingInput,
    classification_is_eligible,
    find_hadith,
    record_ruling,
    verification_queue,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record dorar.net rulings for hadiths.")
    commands = parser.add_subparsers(dest="command", required=True)

    queue = commands.add_parser("queue", help="list the hadiths waiting for a ruling")
    queue.add_argument("--limit", type=int, default=20)

    record = commands.add_parser("record", help="record a ruling for one hadith")
    record.add_argument("collection")
    record.add_argument("number")
    text = record.add_mutually_exclusive_group(required=True)
    text.add_argument("--ruling", help="the ruling text, exactly as dorar gives it")
    text.add_argument("--ruling-file", type=Path, help="a UTF-8 file holding the ruling text")
    record.add_argument("--scholar", required=True)
    record.add_argument("--book", required=True)
    record.add_argument("--page", required=True)
    record.add_argument("--url", required=True, help="the dorar.net page of the ruling")
    record.add_argument(
        "--classification", required=True, choices=[c.value for c in HadithClassification]
    )
    record.add_argument("--editor", required=True)
    return parser


async def _queue(session: AsyncSession, limit: int) -> int:
    waiting = await verification_queue(session, limit)
    if not waiting:
        sys.stdout.write("No hadith is waiting for a ruling.\n")
    for item in waiting:
        sys.stdout.write(
            f"{item.hadith.collection} {item.hadith.number}\twanted {item.demand_count} times\t"
            f"{dorar_search_url(item.hadith.text)}\n"
        )
    return 0


async def _record(session: AsyncSession, args: argparse.Namespace) -> int:
    hadith = await find_hadith(session, args.collection, args.number)
    if hadith is None:
        message = f"no stored hadith {args.collection} {args.number}"
        raise ScriptureError(message)
    ruling_text = (
        args.ruling
        if args.ruling is not None
        else args.ruling_file.read_text(encoding="utf-8").removesuffix("\n")
    )
    ruling = RulingInput(
        ruling_text=ruling_text,
        scholar=args.scholar,
        source_book=args.book,
        page=args.page,
        dorar_url=args.url,
        classification=HadithClassification(args.classification),
        editor_name=args.editor,
    )
    row = await record_ruling(session, hadith.id, ruling)
    eligible = (
        "eligible as evidence"
        if classification_is_eligible(row.classification)
        else ("not eligible as evidence")
    )
    sys.stdout.write(
        f"Recorded ruling {row.id} for {hadith.collection} {hadith.number}: "
        f"{row.classification.value}, {eligible}.\n"
    )
    return 0


async def run(
    argv: Sequence[str] | None = None,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> int:
    """Run one command; return the process exit code."""
    args = _parser().parse_args(argv)
    maker = sessionmaker or get_sessionmaker()
    try:
        async with maker() as session, session.begin():
            if args.command == "queue":
                return await _queue(session, args.limit)
            return await _record(session, args)
    except ValidationError as error:
        fields = ", ".join(str(item["loc"][0]) for item in error.errors())
        sys.stderr.write(f"ruling refused: check {fields}\n")
        return 1
    except ScriptureError as error:
        sys.stderr.write(f"ruling refused: {error}\n")
        return 1
    finally:
        if sessionmaker is None:
            await dispose_engine()


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
