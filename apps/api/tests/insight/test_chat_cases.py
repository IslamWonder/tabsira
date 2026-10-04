"""`make eval`: the twelve chat cases, their scoring, their report and their command, with fake models."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from src.ai.errors import AiCallError, AiErrorCode
from src.ai.records import CallLog
from src.cli import evaluate as command
from src.evaluation.chat_eval import (
    CaseExpectation,
    load_chat_cases,
    run_chat_evaluation,
    score,
)
from src.evaluation.chat_report import render_section
from src.models import ChatMessage
from src.pipeline.insight.guard import quran_detector
from src.pipeline.leak_guard import LeakDetector, LeakFinding, LeakKind
from tests.fakes import FakeModelClient
from tests.scripture.fixtures import verse_text


def said(level: str = "b", answer: str = "تدعو الآية المعروضة إلى النظر.", new: bool = False):
    return {"level": level, "asks_for_new_text": new, "answer": answer}


def cases_file(tmp_path, *cases: dict[str, Any]):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "description": "test",
                "insights": [
                    {
                        "id": "rain",
                        "title": "أثر الرحمة",
                        "glimpse": "المطر يحيي الأرض",
                        "relation": "direct",
                        "quran": {"surah": 30, "ayah": 50},
                        "explanation": [{"section": "seen", "text": "قطرات مطر."}],
                        "why": {"visible_clues": ["قطرات"], "concept": "إحياء", "limits": []},
                    }
                ],
                "cases": list(cases),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def case(identifier: str, source: str = "official", **expect: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "source": source,
        "spec": "§27.16",
        "insight": "rain",
        "question": "في أي سورة هذه الآية؟",
        "expect": {"kinds": ["answer"], **expect},
        "why": "test",
    }


def clients(*answers: Any):
    queue: Iterator[Any] = iter(answers)

    def build(log: CallLog) -> FakeModelClient:
        return FakeModelClient(answers=[next(queue)], log=log)

    return build


def test_the_cases_file_holds_twelve_cases_four_of_them_official(tmp_path):
    cases = load_chat_cases()
    broken = cases_file(tmp_path, case("x") | {"insight": "nowhere"})

    assert len(cases.cases) == 12
    assert len({item.id for item in cases.cases}) == 12
    assert sum(item.source == "official" for item in cases.cases) == 4
    with pytest.raises(ValueError, match="nowhere"):
        load_chat_cases(broken)


def test_an_outcome_is_scored_by_kind_level_words_and_disclosure():
    expect = CaseExpectation(
        kinds=["answer"], levels=["a"], mentions=[["الروم"], ["50", "خمسين"]], avoids=["رواه"]
    )

    def check(**values: Any) -> list[str]:
        outcome = {"kind": "answer", "level": "a", "answer": "", "disclosed": True} | values
        return score(expect, **outcome)

    assert check(answer="الآية في سورة الرُّوم، رقمها \u0665\u0660.") == []
    assert check(answer="سورة الروم") == ["missing 50 / خمسين"]
    assert check(answer="سورة الروم 50، رواه البخاري") == ["says رواه"]
    assert check(answer="سورة الروم 50", disclosed=False) == ["no disclosure"]
    assert check(kind="referral", level="d", answer="الروم 50") == ["kind referral", "level d"]
    assert check(kind="refused", level=None) == ["kind refused", "level none"]
    assert score(CaseExpectation(kinds=["new_search"]), kind="new_search", level="b", answer="x",
                 disclosed=True) == []  # fmt: skip


async def test_each_case_is_asked_in_a_fresh_chat_that_leaves_nothing(
    maker, make_settings, tmp_path
):
    connection = maker.kw["bind"]
    cases = load_chat_cases(
        cases_file(
            tmp_path,
            case("fact", levels=["a"], mentions=[["الروم"]]),
            case("personal", "derived", levels=["d"], kinds=["referral"]),
            case("quoted"),
            case("down"),
            case("unasked"),
        )
    )
    async with maker() as session:
        quran = await quran_detector(session)

    result = await run_chat_evaluation(
        connection,
        make_settings(),
        cases,
        clients(
            said("a", "هي في سورة الروم، رقمها 50."),
            said("d", "هذه حالة شخصية."),
            said("b", f"قال تعالى: {verse_text(30, 50)}"),
            AiCallError(AiErrorCode.TIMEOUT, "slow"),
        ),
        quran,
        only=["fact", "personal", "quoted", "down"],
    )
    capped = await run_chat_evaluation(
        connection, make_settings(), cases, clients(), quran, max_cost_usd=0.0
    )

    runs = {run.case: run for run in result.runs}
    assert list(runs) == ["fact", "personal", "quoted", "down"]
    assert (runs["fact"].kind, runs["fact"].level, runs["fact"].passed) == ("answer", "a", True)
    assert runs["fact"].disclosed
    assert (runs["personal"].kind, runs["personal"].passed) == ("referral", True)
    assert (runs["quoted"].kind, runs["quoted"].level, runs["quoted"].answer) == (
        "refused",
        "b",
        "",
    )
    assert runs["quoted"].model_answer.startswith("قال تعالى")
    assert runs["quoted"].failures == ["kind refused"]
    assert (runs["down"].kind, runs["down"].model_answer) == ("failed", None)
    assert all(not run.leaks for run in result.runs)
    assert capped.runs == []
    async with maker() as session:
        left = await session.scalar(select(func.count()).select_from(ChatMessage))
    assert left == 0
    markdown = render_section(result, "chat.json")
    assert "| Cases as expected | 2 / 4 |" in markdown
    assert "| Official cases as expected | 1 / 3 |" in markdown
    assert "- **quoted**: (refused)" in markdown
    assert "في أي سورة" not in markdown


class FlagsEverything(LeakDetector):
    """A Quran detector that finds scripture in any text, to make the independent check fire."""

    def find(self, text: str) -> list[LeakFinding]:
        return [LeakFinding(kind=LeakKind.CORPUS_OVERLAP, detail="test")]


async def test_an_answer_the_independent_check_flags_fails_and_is_withheld(
    maker, make_settings, tmp_path
):
    cases = load_chat_cases(cases_file(tmp_path, case("fact")))

    result = await run_chat_evaluation(
        maker.kw["bind"],
        make_settings(),
        cases,
        clients(said("a", "هي في سورة الروم.")),
        FlagsEverything(),
    )

    run = result.runs[0]
    assert (run.kind, run.leaks, run.passed) == ("answer", ["answer"], False)
    assert run.failures == ["leak in answer"]
    markdown = render_section(result, "chat.json")
    assert "هي في سورة الروم" not in markdown
    assert "- **fact**: (withheld: the scripture guard flagged it)" in markdown
    assert "| Scripture in an answer shown | 1 |" in markdown


async def test_the_command_asks_the_cases_and_writes_their_section(
    maker, make_settings, tmp_path, capsys
):
    path = cases_file(tmp_path, case("fact", mentions=[["الروم"]]), case("quoted"))
    report = tmp_path / "EVALUATION.md"
    report.write_text("# Evaluation\n\n<!-- section:notes -->\nnotes\n<!-- /section:notes -->\n")
    arguments = [
        "--only", "chat",
        "--chat-cases", str(path),
        "--results-dir", str(tmp_path / "results"),
        "--report", str(report),
    ]  # fmt: skip

    code = await command.run(
        arguments,
        settings=make_settings(),
        sessionmaker=maker,
        connection=maker.kw["bind"],
        chat_clients=clients(said("a", "سورة الروم."), said("b", "جواب")),
        http=httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(503))),
    )

    text = report.read_text(encoding="utf-8")
    assert code == 0
    assert text.startswith("# Evaluation")
    assert "<!-- section:notes -->" in text
    assert "<!-- section:official-cases -->\n## The twelve chat cases" in text
    saved = json.loads(next((tmp_path / "results").glob("chat-*.json")).read_text())
    assert [run["case"] for run in saved["runs"]] == ["fact", "quoted"]
    out = capsys.readouterr().out
    assert "fact: answer, level a, as expected" in out
    assert "chat: 2/2 as expected, 0 leaks" in out


async def test_the_command_opens_and_rolls_back_its_own_connection(
    monkeypatch, engine, maker, make_settings, tmp_path
):
    monkeypatch.setattr(command, "get_engine", lambda: engine)
    path = cases_file(tmp_path, case("fact"))

    code = await command.run(
        ["--only", "chat", "--chat-cases", str(path), "--no-report",
         "--results-dir", str(tmp_path)],
        settings=make_settings(),
        sessionmaker=maker,
        chat_clients=clients(said("a", "سورة الروم.")),
    )  # fmt: skip

    saved = json.loads(next(tmp_path.glob("chat-*.json")).read_text())
    async with engine.connect() as connection:
        left = await connection.scalar(select(func.count()).select_from(ChatMessage))
    assert (code, saved["runs"][0]["kind"], left) == (0, "answer", 0)


async def test_the_command_fails_when_an_answer_shown_holds_scripture(
    monkeypatch, maker, make_settings, tmp_path
):
    async def flagging(_session: Any) -> LeakDetector:
        return FlagsEverything()

    monkeypatch.setattr(command, "quran_detector", flagging)
    path = cases_file(tmp_path, case("fact"))

    code = await command.run(
        ["--only", "chat", "--chat-cases", str(path), "--no-report",
         "--results-dir", str(tmp_path)],
        settings=make_settings(),
        sessionmaker=maker,
        connection=maker.kw["bind"],
        chat_clients=clients(said("a", "سورة الروم.")),
    )  # fmt: skip

    assert code == 1
