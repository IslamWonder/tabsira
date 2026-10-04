"""
Compare the vision models on the gold scenes (make benchmark).

    uv run python -m src.cli.benchmark [--runs N] [--cells NAME,...] [--scenes ID,...]
                                       [--blind-runs N] [--concurrency N] [--max-cost USD]
                                       [--detector-url URL] [--no-report]
    uv run python -m src.cli.benchmark --rescore tests/evaluation/results/<date>.json

It calls the real providers with the keys of the .env, so it costs money; no
new run starts once `--max-cost` dollars are spent. It writes the raw results
(every answer and call record) to tests/evaluation/results/<date>.json, which is
not committed, a summary next to it, and docs/BENCHMARK.md. A provider whose
key is empty fails its cells with `not_configured` and costs nothing.

`--rescore` scores the answers of an earlier raw file again with the current
gold file and judge, and rewrites the outputs: no model is called, only the
local detector (for the box measurement).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from contextlib import AsyncExitStack
from pathlib import Path

import httpx

from src.config import ConfigError, load_settings
from src.evaluation.benchmark import (
    DEFAULT_CELLS,
    BenchmarkOptions,
    BenchmarkResult,
    ClientFactory,
    SavedRun,
    rescore_benchmark,
    run_benchmark,
)
from src.evaluation.gold import load_gold
from src.evaluation.report import render
from src.evaluation.report_sections import carry_sections

API_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = API_DIR.parents[1]
GOLD_PATH = API_DIR / "tests" / "evaluation" / "scenes" / "gold.json"
RESULTS_DIR = API_DIR / "tests" / "evaluation" / "results"
REPORT_PATH = REPO_ROOT / "docs" / "BENCHMARK.md"


def _names(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare the vision models on the gold scenes.")
    parser.add_argument("--runs", type=int, default=2, help="runs per scene and cell (2)")
    parser.add_argument(
        "--cells",
        type=_names,
        default=(),
        help="comma-separated cell names (all): " + ", ".join(c.name for c in DEFAULT_CELLS),
    )
    parser.add_argument("--scenes", type=_names, default=(), help="comma-separated scene ids")
    parser.add_argument(
        "--blind-runs", type=int, default=1, help="runs with the detector hidden (1)"
    )
    parser.add_argument("--concurrency", type=int, default=4, help="calls per provider (4)")
    parser.add_argument("--max-cost", type=float, default=5.0, help="spend cap in USD (5)")
    parser.add_argument("--detector-url", default=None, help="vision service (DETECTOR_URL)")
    parser.add_argument("--gold", type=Path, default=GOLD_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--no-report", action="store_true", help="do not write docs/BENCHMARK.md")
    parser.add_argument(
        "--rescore", type=Path, default=None, help="score a raw results file again, no calls"
    )
    return parser.parse_args(argv)


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def write_outputs(result: BenchmarkResult, args: argparse.Namespace) -> list[Path]:
    """Write the raw results, the summary and (unless asked not to) the report."""
    args.results_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{result.started_at:%Y-%m-%d}"
    raw = args.results_dir / f"{stamp}.json"
    summary = args.results_dir / f"{stamp}-summary.json"
    raw.write_text(result.model_dump_json(indent=1) + "\n", encoding="utf-8")
    summary_data = result.model_dump(mode="json", exclude={"results"})
    summary.write_text(json.dumps(summary_data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    written = [raw, summary]
    if not args.no_report:
        markdown = render(result, load_gold(args.gold), _relative(raw), _relative(args.gold))
        previous = args.report.read_text(encoding="utf-8") if args.report.is_file() else ""
        # Sections other commands own (the retrieval benchmark's) are kept.
        args.report.write_text(carry_sections(previous, markdown), encoding="utf-8")
        written.append(args.report)
    return written


def _report_lines(result: BenchmarkResult, written: Sequence[Path]) -> list[str]:
    lines = [f"{len(result.scenes)} scenes x {result.runs_per_scene} runs"]
    for cell in result.cells:
        p95 = cell.vision_latency.p95
        lines.append(
            f"  {cell.cell.name}: ok {cell.ok}/{cell.runs}, quality {cell.quality}, "
            f"vision p95 {p95} ms, ${cell.cost_usd:.4f}"
            + ("" if cell.eligible else f" (not eligible: {'; '.join(cell.ineligible_because)})")
        )
    lines += [f"  {r.setting}={r.value}" for r in result.recommendations]
    lines.append(f"total spend ${result.total_cost_usd:.4f}")
    lines += [f"wrote {_relative(path)}" for path in written]
    return lines


async def run(
    args: argparse.Namespace,
    *,
    http: httpx.AsyncClient | None = None,
    factory: ClientFactory | None = None,
) -> int:
    """Run the benchmark; return the process exit code."""
    try:
        settings = load_settings()
    except ConfigError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    if args.detector_url:
        settings = settings.model_copy(update={"detector_url": args.detector_url.rstrip("/")})
    known = {cell.name: cell for cell in DEFAULT_CELLS}
    unknown = [name for name in args.cells if name not in known]
    if unknown:
        sys.stderr.write(f"Unknown cell(s): {', '.join(unknown)}. Known: {', '.join(known)}\n")
        return 2
    options = BenchmarkOptions(
        gold_path=args.gold,
        cells=tuple(known[name] for name in args.cells) or DEFAULT_CELLS,
        runs=args.runs,
        blind_runs=args.blind_runs,
        scene_ids=args.scenes,
        concurrency=args.concurrency,
        max_cost_usd=args.max_cost,
    )
    async with AsyncExitStack() as stack:
        client = http if http is not None else await stack.enter_async_context(httpx.AsyncClient())
        if args.rescore:
            saved = SavedRun.model_validate_json(args.rescore.read_text(encoding="utf-8"))
            result = await rescore_benchmark(
                saved, gold_path=args.gold, settings=settings, http=client
            )
        else:
            result = await run_benchmark(options, settings=settings, http=client, factory=factory)
    written = write_outputs(result, args)
    sys.stdout.write("\n".join(_report_lines(result, written)) + "\n")
    return 0 if any(cell.ok for cell in result.cells) else 1


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
