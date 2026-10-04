from __future__ import annotations

import httpx

from src.config import AiProvider, BoxCoordinates
from src.evaluation.benchmark import BenchmarkOptions, run_benchmark
from src.evaluation.gold import load_gold
from src.evaluation.report import render
from tests.benchmark_fixtures import answer, broken, cell, detector_handler, factory, write_gold


async def test_the_report_states_the_method_the_numbers_and_the_choice(tmp_path, make_settings):
    gold_path = write_gold(tmp_path)
    cells = (
        cell("ovh-good"),
        cell("ovh-down"),
        cell(
            "openai-good",
            AiProvider.OPENAI,
            model="gpt-5.4-mini-2026-03-17",
            coordinates=BoxCoordinates.PIXELS,
            guard="omni-moderation-latest",
        ),
    )
    behaviours = {
        "ovh-good": (answer(box=[0, 0, 500, 500], description="طفل يقف"), 20_000),
        "ovh-down": (broken, 1_000),
        "openai-good": (answer(box=[0, 0, 32, 32]), 5_000),
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(detector_handler)) as http:
        result = await run_benchmark(
            BenchmarkOptions(gold_path=gold_path, cells=cells, runs=1),
            settings=make_settings(ai_max_retries=0),
            http=http,
            factory=factory(behaviours),
        )

    text = render(result, load_gold(gold_path), "raw.json", "gold.json")

    assert text.startswith("# Benchmark: scene analysis\n")
    assert "$" not in text.replace(f"${result.total_cost_usd:.4f}", "").replace("$0.", "")
    assert "2 gold scenes from `gold.json`" in text
    assert "(1 sensitive)" in text
    assert "Generated for the test." in text
    assert "plus 1 blind run(s)" in text
    assert "`yoloe-test`, available for 2 of 2 scenes" in text
    assert "| `ovh-good` | ovh | `Qwen3.8-27B` | none | thousandths | scene flags only |" in text
    assert "| `openai-good` | openai |" in text
    assert "`omni-moderation-latest`" in text
    assert "| `ovh-down` | 2/2 | 0% | 0% | n/a | n/a |" in text
    assert "(not eligible)" in text
    assert "| `openai-good` | 5.0 s | 5.0 s | 5.0 s | 5.0 s |" in text
    assert "| `ovh-good` | thousandths | 2 | 2 | 0% | 100% | 1.00 |" in text
    assert "| Detector (HTTP, CPU) | 2 |" in text
    assert "- `ovh-good`: identity word: «طفل» (2)." in text
    assert "- `openai-good`: nothing." in text
    assert "  Failed runs: timeout (2)." in text
    assert "  Not eligible: no valid answer." in text
    assert "| `AI_PROVIDER` | `openai` |" in text
    assert "every answer and call record is in `raw.json`" in text
    assert text.endswith("moderation is free).\n")
