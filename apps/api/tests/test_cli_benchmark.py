"""The benchmark command, with the real adapter on a mock transport: no network, no model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.cli import benchmark as cli
from tests.benchmark_fixtures import answer, detector_handler, write_gold

CELLS = "ovh-qwen3.8-27b,openai-gpt-5.4-mini"


def provider_handler(*, chat_status: int = 200):
    """Answer the detector, both providers' chat completions and OpenAI's moderation."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/detect":
            return detector_handler(request)
        if request.url.path.endswith("/moderations"):
            result = {"flagged": False, "categories": {"sexual": False}, "category_scores": {}}
            return httpx.Response(200, json={"results": [result]})
        if chat_status != 200:
            return httpx.Response(chat_status, json={"error": {"message": "down"}})
        body = json.loads(request.content)
        user = body["messages"][1]["content"][0]["text"]
        box = [0, 0, 500, 500] if "0-1000 grid" in user else [0, 0, 32, 32]
        content = json.dumps(answer(box=box)({"user": user}), ensure_ascii=False)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
            },
        )

    return handle


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("AI_OVH__API_KEY", "ovh-test-key")
    monkeypatch.setenv("AI_OPENAI__API_KEY", "openai-test-key")
    monkeypatch.setenv("AI_MAX_RETRIES", "0")


def arguments(tmp_path: Path, *extra: str, detector: bool = True) -> list[str]:
    gold = write_gold(tmp_path)
    url = ["--detector-url", "http://127.0.0.1:8100/"] if detector else []
    return [
        "--runs",
        "1",
        "--cells",
        CELLS,
        "--gold",
        str(gold),
        "--results-dir",
        str(tmp_path / "results"),
        "--report",
        str(tmp_path / "BENCHMARK.md"),
        *url,
        *extra,
    ]


async def run(argv: list[str], handler) -> int:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        return await cli.run(cli.parse_args(argv), http=http)


def test_arguments_default_to_every_cell_and_two_runs():
    args = cli.parse_args([])

    assert (args.runs, args.blind_runs, args.concurrency, args.max_cost) == (2, 1, 4, 5.0)
    assert args.cells == ()
    assert args.gold == cli.GOLD_PATH
    assert args.report == cli.REPO_ROOT / "docs" / "BENCHMARK.md"
    assert cli.parse_args(["--cells", " a, ,b "]).cells == ("a", "b")


async def test_a_run_writes_the_raw_results_the_summary_and_the_report(tmp_path, keys, capsys):
    code = await run(arguments(tmp_path), provider_handler())

    assert code == 0
    (summary_path,) = (tmp_path / "results").glob("*-summary.json")
    raw_path = summary_path.with_name(summary_path.name.replace("-summary", ""))
    raw = json.loads(raw_path.read_text())
    summary = json.loads(summary_path.read_text())
    assert len(raw["results"]) == 8
    assert "results" not in summary
    assert [c["cell"]["name"] for c in summary["cells"]] == CELLS.split(",")
    assert all(c["ok"] == 2 for c in summary["cells"])
    report = (tmp_path / "BENCHMARK.md").read_text()
    assert "# Benchmark: scene analysis" in report
    assert "`ovh-qwen3.8-27b`" in report
    out = capsys.readouterr().out
    assert out.startswith("2 scenes x 1 runs\n")
    assert "  ovh-qwen3.8-27b: ok 2/2" in out
    assert "  AI_OVH__VISION_MODEL=Qwen3.8-27B" in out
    assert "total spend $" in out
    assert "wrote " in out
    assert "test-key" not in out + report + json.dumps(raw)


async def test_a_saved_run_can_be_scored_again_without_calls(tmp_path, keys, capsys):
    assert await run(arguments(tmp_path, "--no-report"), provider_handler()) == 0
    (raw,) = [p for p in (tmp_path / "results").glob("*.json") if "summary" not in p.name]
    capsys.readouterr()

    def detector_only(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/detect"
        return detector_handler(request)

    code = await run(arguments(tmp_path, "--rescore", str(raw)), detector_only)

    assert code == 0
    assert (tmp_path / "BENCHMARK.md").exists()
    assert "  ovh-qwen3.8-27b: ok 2/2" in capsys.readouterr().out


async def test_the_report_can_be_left_alone(tmp_path, keys):
    code = await run(arguments(tmp_path, "--no-report"), provider_handler())

    assert code == 0
    assert not (tmp_path / "BENCHMARK.md").exists()


async def test_a_run_where_nothing_answers_fails_and_says_why(tmp_path, keys, capsys):
    code = await run(arguments(tmp_path), provider_handler(chat_status=503))

    assert code == 1
    out = capsys.readouterr().out
    assert "not eligible: no valid answer" in out


async def test_an_unknown_cell_is_refused(tmp_path, keys, capsys):
    code = await run([*arguments(tmp_path), "--cells", "nope"], provider_handler())

    assert code == 2
    assert "Unknown cell(s): nope" in capsys.readouterr().err


async def test_a_bad_configuration_stops_before_any_call(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL")

    code = await run(arguments(tmp_path), provider_handler())

    assert code == 1
    assert "DATABASE_URL" in capsys.readouterr().err


async def test_without_a_client_it_opens_and_closes_its_own(tmp_path, keys, monkeypatch):
    real = httpx.AsyncClient
    opened: list[Any] = []

    def make() -> httpx.AsyncClient:
        client = real(transport=httpx.MockTransport(provider_handler()))
        opened.append(client)
        return client

    monkeypatch.setattr(cli.httpx, "AsyncClient", make)

    code = await cli.run(cli.parse_args(arguments(tmp_path, "--no-report", detector=False)))

    assert code == 0
    assert opened[0].is_closed


def test_main_runs_the_command(monkeypatch):
    seen = []

    async def fake_run(args):
        seen.append(args.runs)
        return 3

    monkeypatch.setattr(cli, "run", fake_run)

    assert cli.main(["--runs", "5"]) == 3
    assert seen == [5]


def test_paths_outside_the_repository_are_written_in_full():
    assert cli._relative(Path("/elsewhere/raw.json")) == "/elsewhere/raw.json"
    assert cli._relative(cli.REPORT_PATH) == "docs/BENCHMARK.md"
