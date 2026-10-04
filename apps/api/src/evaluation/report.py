"""Write docs/BENCHMARK.md from a benchmark result and report_template.txt."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from string import Template

from src.evaluation.benchmark import (
    AGREEMENT_IOU,
    MAX_BOX_DROP_RATE,
    MIN_DETECTOR_IOU,
    MIN_VALID_RATE,
    QUALITY_MARGIN,
    BenchmarkResult,
    CellSummary,
    Stat,
)
from src.evaluation.gold import GoldSet

TEMPLATE = Path(__file__).with_name("report_template.txt")
TOP_FINDINGS = 6


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _seconds(value: int | None) -> str:
    return "n/a" if value is None else f"{value / 1000:.1f} s"


def _usd(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.4f}"


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _stat_row(name: str, value: Stat) -> list[str]:
    return [name, str(value.count), _seconds(value.p50), _seconds(value.p95), _seconds(value.mean)]


def _cell_row(c: CellSummary) -> list[str]:
    guard = f"`{c.cell.guard_model}`" if c.cell.guard_model else "scene flags only"
    return [
        f"`{c.cell.name}`",
        c.cell.provider.value,
        f"`{c.cell.model}`",
        c.cell.reasoning_effort or "provider default",
        c.cell.box_coordinates.value,
        guard,
        c.cell.role,
    ]


def _quality_row(c: CellSummary) -> list[str]:
    sensitive = (
        f"{_pct(c.sensitive_accuracy)} "
        f"({c.sensitive_false_negatives}/{c.sensitive_false_positives})"
    )
    quality = _num(c.quality) + ("" if c.eligible else " (not eligible)")
    return [
        f"`{c.cell.name}`",
        f"{c.runs - c.skipped}/{c.runs}",
        _pct(c.schema_valid_rate),
        _pct(c.first_try_rate),
        _pct(c.entity_recall),
        _pct(c.action_recall),
        str(c.forbidden_claims),
        str(c.identity_inferences),
        str(c.hallucinated_entities),
        sensitive,
        _pct(c.clarification_agreement),
        _pct(c.box_drop_rate),
        _num(c.detector_iou_median),
        quality,
    ]


def _cost_row(c: CellSummary) -> list[str]:
    return [
        f"`{c.cell.name}`",
        _seconds(c.vision_latency.p50),
        _seconds(c.vision_latency.p95),
        _seconds(c.guard_latency.p50),
        _seconds(c.guard_latency.p95),
        _num(c.input_tokens_mean, 0),
        _num(c.output_tokens_mean, 0),
        _num(c.reasoning_tokens_mean, 0),
        _usd(c.cost_per_scan_usd),
        _usd(c.cost_usd),
    ]


def _blind_row(c: CellSummary) -> list[str]:
    return [
        f"`{c.cell.name}`",
        c.cell.box_coordinates.value,
        str(c.blind_runs),
        str(c.blind_boxes_given),
        _pct(c.blind_box_drop_rate),
        _pct(c.blind_box_agreement),
        _num(c.blind_iou_median),
    ]


def _findings(cells: Sequence[CellSummary]) -> str:
    lines: list[str] = []
    for c in cells:
        top = list(c.findings.items())[:TOP_FINDINGS]
        details = "; ".join(f"{text} ({count})" for text, count in top) or "nothing"
        lines.append(f"- `{c.cell.name}`: {details}.")
        if c.errors:
            failures = "; ".join(f"{code} ({count})" for code, count in c.errors.items())
            lines.append(f"  Failed runs: {failures}.")
        if c.ineligible_because:
            lines.append(f"  Not eligible: {'; '.join(c.ineligible_because)}.")
    return "\n".join(lines)


def render(result: BenchmarkResult, gold: GoldSet, raw_path: str, gold_path: str) -> str:
    """Return the Markdown of docs/BENCHMARK.md."""
    sensitive = sum(1 for scene in gold.scenes if scene.sensitive and scene.id in result.scenes)
    minutes = (result.finished_at - result.started_at).total_seconds() / 60
    values = {
        "date": f"{result.started_at:%d %B %Y}",
        "duration": f"{minutes:.0f}",
        "raw_path": raw_path,
        "gold_path": gold_path,
        "scene_count": len(result.scenes),
        "sensitive_count": sensitive,
        "provenance_note": gold.provenance_note,
        "runs": result.runs_per_scene,
        "blind_runs": result.blind_runs_per_scene,
        "agreement_iou": AGREEMENT_IOU,
        "detector_model": result.detector_model or "unavailable",
        "detector_available": result.detector_available,
        "prompt_version": result.prompt_version or "n/a",
        "cells_table": _table(
            ["Cell", "Provider", "Model", "Reasoning", "Boxes", "Guard", "Role"],
            (_cell_row(c) for c in result.cells),
        ),
        "min_valid": f"{MIN_VALID_RATE:.0%}",
        "max_drop": f"{MAX_BOX_DROP_RATE:.0%}",
        "min_iou": MIN_DETECTOR_IOU,
        "margin": QUALITY_MARGIN,
        "quality_table": _table(
            [
                "Cell",
                "Runs",
                "Valid",
                "First try",
                "Entity recall",
                "Action recall",
                "Forbidden",
                "Identity",
                "Invented",
                "Sensitive (FN/FP)",
                "Question",
                "Boxes out",
                "IoU vs detector",
                "Quality",
            ],
            (_quality_row(c) for c in result.cells),
        ),
        "cost_table": _table(
            [
                "Cell",
                "Vision p50",
                "Vision p95",
                "Guard p50",
                "Guard p95",
                "Input tokens",
                "Output tokens",
                "of which reasoning",
                "Cost per scan",
                "Cell total",
            ],
            (_cost_row(c) for c in result.cells),
        ),
        "blind_table": _table(
            [
                "Cell",
                "Asked in",
                "Runs",
                "Boxes",
                "Outside",
                "On a detector box",
                "Median best IoU",
            ],
            (_blind_row(c) for c in result.cells),
        ),
        "stage_table": _table(
            ["Stage", "Samples", "p50", "p95", "Mean"],
            [
                _stat_row("Image validation", result.validation_latency),
                _stat_row("Detector (HTTP, CPU)", result.detector_latency),
            ],
        ),
        "findings": _findings(result.cells),
        "recommendations_table": _table(
            ["Setting", "Value", "Why"],
            ([f"`{r.setting}`", f"`{r.value}`", r.reason] for r in result.recommendations),
        ),
        "total_cost": _usd(result.total_cost_usd),
    }
    return Template(TEMPLATE.read_text(encoding="utf-8")).substitute(values)
