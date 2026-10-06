"""
Import the scripture store from its verified sources.

    uv run python -m src.cli.import_scripture [STEP ...] [--cache-dir DIR] [--corpus-dir DIR]

Steps run in the order given; with none, all of them in this order:

    download     fetch quranpedia's current dump, checked against its manifest,
                 and the nine hadith files from their pinned commits
    quran        import mushaf 2 from the newest verified dump in the cache
    standard     bring every verse's guard skeleton in today's spelling in line with
                 its stored text (derived, leak guard only; writes nothing when it is
                 current, so make data and every deploy run it)
    annotations  import the annotations of data/corpus/quran-annotations.json
    hadith       import the nine books from their pinned, verified files
    signals      repair data/corpus/sunnah-enriched.json and link its records to hadiths

Every step can run again: what is already stored and unchanged stays as it is.
Each step writes in one transaction (the scripture steps with the guard open),
so a step that fails leaves the database as it was. Exit 0 on success, 1 on
failure.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database import dispose_engine, get_sessionmaker
from src.scripture import hadith as hadith_store
from src.scripture.annotations import (
    ANNOTATIONS_FILE,
    ANNOTATIONS_SHA256,
    import_annotations,
)
from src.scripture.errors import ScriptureError
from src.scripture.files import require_verified
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.paths import DEFAULT_CACHE_DIR, DEFAULT_CORPUS_DIR
from src.scripture.quran import (
    QuranImportError,
    import_quran,
    load_json_file,
    parse_mushaf,
    refresh_standard_guard,
)
from src.scripture.quran import parse_surahs as parse_surah_information
from src.scripture.quranpedia import (
    MUSHAF_FILE,
    QuranpediaClient,
    QuranpediaError,
    cached_dump_files,
    dump_url,
    fetch_dump_files,
    new_http_client,
)
from src.scripture.sunnah import SUNNAH_FILE, SUNNAH_SHA256, import_signals, repair

log = logging.getLogger("tabsira.scripture.import")


@dataclass(frozen=True)
class Context:
    cache_dir: Path
    corpus_dir: Path
    sessionmaker: async_sessionmaker[AsyncSession]
    http: httpx.AsyncClient


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


async def step_download(context: Context) -> None:
    """Download what the cache lacks; with no network, a verified cached dump is enough."""
    try:
        files = await fetch_dump_files(QuranpediaClient(context.http), context.cache_dir)
    except QuranpediaError as error:
        cached = cached_dump_files(context.cache_dir)
        if cached is None:
            raise
        log.warning(
            "quranpedia unreachable (%s); keeping the cached dump %s", error, cached.version
        )
        files = cached
    _say(f"download: quranpedia dump {files.version} verified")
    for source in hadith_store.COLLECTIONS:
        await hadith_store.ensure_source_file(context.http, context.cache_dir, source)
    _say(f"download: {len(hadith_store.COLLECTIONS)} hadith files verified")


async def step_quran(context: Context) -> None:
    files = cached_dump_files(context.cache_dir)
    if files is None:
        message = f"no verified quranpedia dump in {context.cache_dir}; run the download step first"
        raise QuranImportError(message)
    dump = parse_mushaf(load_json_file(files.mushaf))
    if not dump.is_complete():
        message = f"the dump {files.version} is not a whole mushaf; refusing to import it"
        raise QuranImportError(message)
    surahs = parse_surah_information(load_json_file(files.surahs))
    async with context.sessionmaker() as session, session.begin():
        await allow_scripture_writes(session, WritePurpose.IMPORT)
        report = await import_quran(
            session,
            dump,
            surahs,
            dump_sha256=files.mushaf_sha256,
            source=f"{dump_url(MUSHAF_FILE)} version {files.version}",
        )
    _say(
        f"quran: dump {report.version}, {report.surahs} surahs, {report.inserted} inserted, "
        f"{report.corrected} corrected, {report.unchanged} unchanged, "
        f"{report.metadata_updated} with new page facts"
    )


async def step_standard(context: Context) -> None:
    async with context.sessionmaker() as session, session.begin():
        changed = await refresh_standard_guard(session)
    _say(f"standard: {changed} verse skeletons in today's spelling written, the others current")


async def step_annotations(context: Context) -> None:
    path = require_verified(context.corpus_dir / ANNOTATIONS_FILE, ANNOTATIONS_SHA256)
    raw = load_json_file(path)
    async with context.sessionmaker() as session, session.begin():
        report = await import_annotations(session, raw, ANNOTATIONS_SHA256)
    _say(
        f"annotations: {report.verses} verses annotated, {report.echoes_left_out} strings "
        "repeating their verse left out"
    )


async def step_hadith(context: Context) -> None:
    parsed = [
        (
            source,
            hadith_store.parse_source(
                source,
                require_verified(source.cache_path(context.cache_dir), source.sha256).read_bytes(),
            ),
        )
        for source in hadith_store.COLLECTIONS
    ]
    async with context.sessionmaker() as session, session.begin():
        await allow_scripture_writes(session, WritePurpose.IMPORT)
        reports = [
            await hadith_store.import_collection(session, source, records)
            for source, records in parsed
        ]
    for report in reports:
        _say(
            f"hadith: {report.slug}, {report.inserted} inserted, {report.unchanged} unchanged, "
            f"{report.skipped_empty} with an empty text in the source not stored"
        )


async def step_signals(context: Context) -> None:
    path = require_verified(context.corpus_dir / SUNNAH_FILE, SUNNAH_SHA256)
    raw = load_json_file(path)
    records = repair(raw["results"])
    async with context.sessionmaker() as session, session.begin():
        report = await import_signals(
            session,
            records,
            model=repair(raw["metadata"]["model_used"]),
            source_sha256=SUNNAH_SHA256,
        )
    _say(
        f"signals: {report.records} records repaired losslessly, {report.linked} linked to a hadith, "
        f"{report.records - report.linked} without a match"
    )


STEPS: dict[str, Callable[[Context], Awaitable[None]]] = {
    "download": step_download,
    "quran": step_quran,
    "standard": step_standard,
    "annotations": step_annotations,
    "hadith": step_hadith,
    "signals": step_signals,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import the scripture store.")
    parser.add_argument("steps", nargs="*", metavar="STEP", help=", ".join(STEPS))
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    return parser


async def run(
    argv: Sequence[str] | None = None,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    http: httpx.AsyncClient | None = None,
) -> int:
    """Run the steps; return the process exit code."""
    parser = _parser()
    args = parser.parse_args(argv)
    unknown = [step for step in args.steps if step not in STEPS]
    if unknown:
        parser.error(f"unknown step {', '.join(unknown)}; the steps are {', '.join(STEPS)}")
    steps = args.steps or list(STEPS)
    try:
        async with http or new_http_client() as client:
            context = Context(
                cache_dir=args.cache_dir,
                corpus_dir=args.corpus_dir,
                sessionmaker=sessionmaker or get_sessionmaker(),
                http=client,
            )
            for step in steps:
                await STEPS[step](context)
    except ScriptureError as error:
        sys.stderr.write(f"import failed: {error}\n")
        return 1
    finally:
        if sessionmaker is None:
            await dispose_engine()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
