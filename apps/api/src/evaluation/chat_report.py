"""Write the chat cases' section of docs/EVALUATION.md from a chat evaluation result."""

from __future__ import annotations

from pathlib import Path
from string import Template

from src.evaluation.chat_eval import ChatCaseRun, ChatEvaluationResult
from src.evaluation.retrieval_report import _table

SECTION = "official-cases"
TEMPLATE = Template(
    Path(__file__).with_name("chat_report_template.txt").read_text(encoding="utf-8")
)
HEADERS = [
    "Case",
    "Source",
    "Spec",
    "Accepts",
    "Outcome",
    "Level",
    "As expected",
    "Why not",
    "Time",
]


def _row(run: ChatCaseRun) -> list[str]:
    return [
        run.case,
        run.source,
        run.spec,
        run.expected,
        f"`{run.kind}`",
        run.level or "—",
        "yes" if run.passed else "no",
        "; ".join(run.failures) or "—",
        f"{run.total_ms / 1000:.1f} s",
    ]


def _passed(runs: list[ChatCaseRun], source: str | None = None) -> str:
    chosen = [run for run in runs if source is None or run.source == source]
    return f"{sum(run.passed for run in chosen)} / {len(chosen)}"


# A question may hold a learner's wrong wording of a verse, so it stays in cases.json.
WITHHELD = "(withheld: the scripture guard flagged it)"


def _answers(runs: list[ChatCaseRun]) -> str:
    """List the text each case showed, so a person can judge what the rules cannot."""
    lines = []
    for run in runs:
        if run.leaks:
            shown = WITHHELD
        elif run.answer:
            shown = " ".join(run.answer.split())
        else:
            shown = f"({run.kind})"
        lines.append(f"- **{run.case}**: {shown}")
    return "\n".join(lines)


def render_section(result: ChatEvaluationResult, raw_path: str) -> str:
    """Return the Markdown of the section, without its markers."""
    runs = result.runs
    return TEMPLATE.substitute(
        date=f"{result.started_at:%d %B %Y}",
        provider=result.provider,
        model=result.model,
        raw_path=raw_path,
        passed=_passed(runs),
        official=_passed(runs, "official"),
        derived=_passed(runs, "derived"),
        leaks=sum(len(run.leaks) for run in runs),
        refused=sum(run.kind == "refused" for run in runs),
        cost=f"{result.cost_usd:.4f}",
        case_table=_table(HEADERS, (_row(run) for run in runs)),
        answers=_answers(runs),
    )
