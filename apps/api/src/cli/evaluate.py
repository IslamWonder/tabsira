"""
Evaluate the insight engine on the gold scenes (`make eval`).

    uv run python -m src.cli.evaluate [--scenes a,b] [--max-cost USD] [--no-report]

Every gold scene goes through the whole scan pipeline with the active
provider (the keys of the root .env): image check, detector, scene analysis,
sensitivity guard, insight engine. It costs money (about three cents a scene
with the defaults); `--max-cost` stops before a scene once that much is spent.
The raw results go to `tests/evaluation/results/evaluation-<date>.json` (not
committed) and the report to docs/EVALUATION.md. Exit 0 when no scripture
leaked and every reference resolved, 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ai.client import ModelClient, client_for
from src.ai.records import CallLog
from src.config import AiStage, Settings, get_settings
from src.database import dispose_engine, get_sessionmaker
from src.evaluation.benchmark import prepare_scenes
from src.evaluation.engine_eval import (
    ENGINE_GOLD,
    EngineFactory,
    SceneRun,
    load_engine_gold,
    run_evaluation,
    summary,
)
from src.evaluation.evaluation_report import render
from src.evaluation.gold import load_gold
from src.pipeline.detector import DetectorClient
from src.pipeline.engine import InsightEngine
from src.pipeline.insight.engine import ResourceCache, build_engine
from src.pipeline.insight.guard import quran_detector

API_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = API_DIR.parents[1]
SCENES_DIR = API_DIR / "tests" / "evaluation" / "scenes"
RESULTS_DIR = API_DIR / "tests" / "evaluation" / "results"
REPORT_PATH = REPO_ROOT / "docs" / "EVALUATION.md"
STAGES = (AiStage.VISION, AiStage.PLANNER, AiStage.VERIFY, AiStage.COMPOSE, AiStage.EMBEDDING)


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the insight engine on the gold scenes.")
    parser.add_argument("--scenes", default="", help="scene ids, comma separated (default: all)")
    parser.add_argument("--max-cost", type=float, default=2.0)
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--gold", type=Path, default=ENGINE_GOLD, help=argparse.SUPPRESS)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.scenes = [name for name in args.scenes.split(",") if name]
    return args


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def factory_for(
    settings: Settings, http: httpx.AsyncClient, maker: async_sessionmaker[AsyncSession]
) -> EngineFactory:
    shared = ResourceCache()

    def build(log: CallLog) -> tuple[ModelClient, InsightEngine]:
        engine = build_engine(settings, http, maker, log=log, resources=shared)
        return client_for(settings, http, log=log), engine

    return build


async def _progress(run: SceneRun) -> None:
    _say(
        f"{run.scene}: {run.status}, {run.insights} insights, "
        f"{run.total_ms / 1000:.1f} s, ${run.cost_usd:.4f}"
    )


async def run(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    factory: EngineFactory | None = None,
    http: httpx.AsyncClient | None = None,
) -> int:
    """Run the evaluation; return the process exit code."""
    args = parse_args(argv)
    settings = settings or get_settings()
    gold = load_engine_gold(args.gold)
    maker = sessionmaker or get_sessionmaker()
    try:
        async with http or httpx.AsyncClient() as transport, maker() as session:
            detector = DetectorClient(
                settings.detector_url, transport, timeout_seconds=settings.detector_timeout_seconds
            )
            scenes = await prepare_scenes(
                load_gold(SCENES_DIR / "gold.json"),
                SCENES_DIR,
                args.scenes,
                settings=settings,
                detector=detector,
            )
            result = await run_evaluation(
                session,
                scenes,
                gold,
                factory or factory_for(settings, transport, maker),
                await quran_detector(session),
                provider=settings.ai_provider.value,
                models={stage.value: settings.ai.model_for(stage) for stage in STAGES},
                max_cost_usd=args.max_cost,
                on_scene=_progress,
            )
    finally:
        if sessionmaker is None:
            await dispose_engine()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    raw = args.results_dir / f"evaluation-{result.started_at:%Y-%m-%d}.json"
    raw.write_text(result.model_dump_json(indent=1) + "\n", encoding="utf-8")
    if not args.no_report:
        args.report.write_text(render(result, _relative(raw)), encoding="utf-8")
    facts = summary(result)
    _say(
        f"{facts.correct}/{facts.scenes} as expected, {facts.leaks} leaks, "
        f"{facts.unresolved}/{facts.evidence} unresolved, ${facts.cost:.4f}"
    )
    return 0 if facts.leaks == 0 and facts.unresolved == 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
