"""Write docs/EVALUATION.md from an engine evaluation result."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from string import Template

from src.evaluation.engine_eval import EvaluationResult, SceneRun, summary
from src.evaluation.retrieval_report import _table

TEMPLATE = Template(
    Path(__file__).with_name("evaluation_report_template.txt").read_text(encoding="utf-8")
)


def _ratio(found: object, total: object) -> str:
    return f"{found} / {total}"


def _counts(counter: Mapping[str, int]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"`{name}` {count}" for name, count in sorted(counter.items()))


def _scene_row(run: SceneRun) -> list[str]:
    return [
        run.scene,
        run.expected,
        f"`{run.status}`",
        "yes" if run.correct else "no",
        ", ".join(f"`{key}`" for key in run.evidence) or "—",
        ", ".join(run.relations) or "—",
        f"{run.total_ms / 1000:.1f} s",
        f"${run.cost_usd:.4f}",
    ]


def render(result: EvaluationResult, raw_path: str) -> str:
    """Return the Markdown of docs/EVALUATION.md."""
    facts = summary(result)
    models = ", ".join(f"{stage}: `{model}`" for stage, model in sorted(result.models.items()))
    return TEMPLATE.substitute(
        date=f"{result.started_at:%d %B %Y}",
        provider=result.provider,
        models=models,
        raw_path=raw_path,
        scenes=facts.scenes,
        detector=result.detector_available,
        leaks=facts.leaks,
        resolved=_ratio(facts.evidence - facts.unresolved, facts.evidence),
        correct=_ratio(facts.correct, facts.scenes),
        abstain=_ratio(facts.abstain_correct, facts.abstain_expected),
        insight=_ratio(facts.insight_correct, facts.insight_expected),
        hoped=_ratio(facts.hoped_found, facts.hoped),
        cost_per_scan=f"{facts.cost_per_scan:.4f}",
        cost=f"{facts.cost:.4f}",
        statuses=_counts(facts.statuses),
        relations=_counts(facts.relations),
        stage_table=_table(
            ["Stage", "p50", "p95"],
            (
                [name, f"{p50 / 1000:.1f} s", f"{p95 / 1000:.1f} s"]
                for name, (p50, p95) in facts.stages.items()
            ),
        ),
        scene_table=_table(
            ["Scene", "Expected", "Status", "As expected", "Evidence", "Relations", "Time", "Cost"],
            (_scene_row(run) for run in result.runs),
        ),
    )
