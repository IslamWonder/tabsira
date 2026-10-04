"""The retrieval benchmark: gold set, methods, merge, report and command."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from src.cli import retrieval_benchmark as command
from src.config import AiProvider
from src.evaluation.report_sections import carry_sections, replace_section, sections, wrap
from src.evaluation.retrieval_benchmark import (
    EmbeddingCell,
    LatencyStat,
    MethodScore,
    QueryRanks,
    RetrievalBenchmarkResult,
    concept_overlap,
    first_rank,
    latency,
    reference_blend,
    run_retrieval_benchmark,
    score,
)
from src.evaluation.retrieval_gold import (
    RETRIEVAL_GOLD,
    GoldError,
    ResolvedQuery,
    load_retrieval_gold,
    resolve_gold,
)
from src.evaluation.retrieval_report import best, merge, recommendations, render
from src.models import EmbeddedCorpus, Hadith, QuranVerse, QuranVerseEmbedding
from src.retrieval.concepts import load_concept_index
from src.retrieval.documents import RetrievalDocument
from src.retrieval.lexical import LexicalMethod
from tests.retrieval.support import EmbeddingClient, fake_vector

CELL = EmbeddingCell(name="fake", provider=AiProvider.OPENAI, model="fake-embed", dimensions=8)
OVH_CELL = EmbeddingCell(name="fake-ovh", provider=AiProvider.OVH, model="fake-embed", dimensions=8)


def test_the_committed_gold_set_has_enough_distinct_queries_of_both_corpora():
    gold = load_retrieval_gold()

    corpora = [query.corpus for query in gold.queries]
    assert len(gold.queries) >= 40
    assert {"quran", "hadith"} == set(corpora)
    assert gold.hadith_collections == ["bukhari", "muslim"]
    assert RETRIEVAL_GOLD.name == "gold.json"


def test_a_gold_set_with_a_repeated_id_is_refused(tmp_path):
    raw = json.loads(RETRIEVAL_GOLD.read_text())
    raw["queries"] = [raw["queries"][0], raw["queries"][0]]
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(raw))

    with pytest.raises(GoldError, match="twice"):
        load_retrieval_gold(path)


async def test_gold_answers_resolve_to_stored_ids_or_stop_the_run(world, tmp_path):
    raw = json.loads(RETRIEVAL_GOLD.read_text())
    raw["queries"] = [
        {
            "id": "a",
            "corpus": "quran",
            "query": "إحياء الأرض",
            "relevant": ["Q:30:50"],
            "source": "t",
        },
        {
            "id": "b",
            "corpus": "hadith",
            "query": "المطر",
            "relevant": ["H:bukhari:1032"],
            "source": "t",
        },
    ]
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(raw))
    gold = load_retrieval_gold(path)

    resolved = await resolve_gold(world, gold)
    raw["queries"][0]["relevant"] = ["Q:99:1"]
    path.write_text(json.dumps(raw))

    assert [query.corpus for query in resolved] == [EmbeddedCorpus.QURAN, EmbeddedCorpus.HADITH]
    assert all(len(query.relevant_ids) == 1 for query in resolved)
    with pytest.raises(GoldError, match="Q:99:1"):
        await resolve_gold(world, load_retrieval_gold(path))


def test_scores_count_recall_at_each_cutoff_and_mrr():
    item = score("m", "all", [1, 2, 5, None])

    assert (item.recall_at_1, item.recall_at_3, item.recall_at_10, item.recall_at_30) == (
        0.25,
        0.5,
        0.75,
        0.75,
    )
    assert item.mrr_at_10 == pytest.approx((1 + 0.5 + 0.2) / 4)
    assert score("m", "all", []).queries == 0
    assert first_rank([5, 6, 7], frozenset({7})) == 3
    assert first_rank([5], frozenset({7})) is None
    assert latency("x", []).p50_ms == 0.0
    assert latency("x", [0.1, 0.3]).p95_ms == pytest.approx(300.0)


def test_the_reference_blend_and_the_concept_overlap():
    document = RetrievalDocument(EmbeddedCorpus.QURAN, 1, "نص", ("إحياء الأرض",))

    assert concept_overlap("إحياء الأرض بالمطر", document) == pytest.approx(2 / 3)
    assert concept_overlap("من في", document) == 0.0
    assert reference_blend(1.0, 1.0, 1.0) == pytest.approx(1.0)


async def _queries(session) -> list[ResolvedQuery]:
    verse = await session.scalar(
        select(QuranVerse.id).where(QuranVerse.surah == 30, QuranVerse.ayah == 50)
    )
    hadith = await session.scalar(
        select(Hadith.id).where(Hadith.collection == "bukhari", Hadith.number == "1032")
    )
    return [
        ResolvedQuery(
            id="q",
            corpus=EmbeddedCorpus.QURAN,
            query="إحياء الأرض",
            relevant_ids=frozenset({verse}),
        ),
        ResolvedQuery(
            id="h",
            corpus=EmbeddedCorpus.HADITH,
            query="الدعاء عند المطر",
            relevant_ids=frozenset({hadith}),
        ),
    ]


async def test_every_method_and_reranker_is_scored_on_every_query(world):
    queries = await _queries(world)
    verse = next(iter(queries[0].relevant_ids))
    world.add(
        QuranVerseEmbedding(
            verse_id=verse,
            model="fake-embed",
            dimensions=8,
            document_sha256="0" * 64,
            embedding=fake_vector("إحياء الأرض"),
        )
    )
    await world.flush()
    concepts = {corpus: await load_concept_index(world, corpus) for corpus in EmbeddedCorpus}

    async def by_length(_query: str, passages: Sequence[str]) -> list[float]:
        return [len(text) / 1000 for text in passages]

    result = await run_retrieval_benchmark(
        world,
        queries,
        cells=[CELL, OVH_CELL],
        clients={
            AiProvider.OPENAI: EmbeddingClient(),
            AiProvider.OVH: EmbeddingClient(AiProvider.OVH),
        },
        concepts=concepts,
        hadith_collections=["bukhari"],
        lexical_methods=[LexicalMethod.TRIGRAM],
        rerankers={"length": by_length},
        rerank_cell="fake",
    )

    methods = {item.method for item in result.scores}
    assert {
        "fts",
        "trigram",
        "concepts",
        "vector:fake",
        "hybrid:fake",
        "hybrid+concepts:fake",
        "rerank:length",
        "rerank:length+metadata",
    } <= methods
    assert result.per_query[0].ranks["vector:fake"] == 1
    assert result.rerank_cell == "fake"
    assert result.cost_usd > 0
    assert any(item.name == "rerank 30: length" for item in result.latencies)


async def test_without_rerankers_no_rerank_cell_is_reported(world):
    concepts = {corpus: await load_concept_index(world, corpus) for corpus in EmbeddedCorpus}

    result = await run_retrieval_benchmark(
        world,
        await _queries(world),
        cells=[CELL],
        clients={AiProvider.OPENAI: EmbeddingClient()},
        concepts=concepts,
        hadith_collections=["bukhari"],
        rerank_cell="fake",
    )

    assert result.rerank_cell is None
    assert not any(item.method.startswith("rerank") for item in result.scores)


def _result(
    methods: dict[str, float], *, cells=(CELL, OVH_CELL), cost: float = 0.01, day: int = 4
) -> RetrievalBenchmarkResult:
    return RetrievalBenchmarkResult(
        started_at=datetime(2026, 10, day, tzinfo=UTC),
        finished_at=datetime(2026, 10, day, tzinfo=UTC),
        queries=2,
        hadith_collections=["bukhari"],
        cells=list(cells),
        rerank_cell="fake",
        scores=[
            MethodScore(
                method=name,
                corpus=corpus,
                queries=2,
                recall_at_1=mrr,
                recall_at_3=mrr,
                recall_at_10=mrr,
                recall_at_30=mrr,
                mrr_at_10=mrr,
            )
            for name, mrr in methods.items()
            for corpus in ("quran", "all")
        ],
        latencies=[
            LatencyStat(name=f"t:{name}", samples=1, p50_ms=1, p95_ms=2) for name in methods
        ],
        per_query=[QueryRanks(id="q", corpus="quran", ranks=dict.fromkeys(methods, 1))],
        cost_usd=cost,
    )


def test_a_merge_keeps_what_the_new_run_did_not_measure_again():
    first = _result({"vector:fake": 0.5, "rerank:a": 0.4})
    second = _result({"vector:fake": 0.6, "rerank:b": 0.7}, cells=(CELL,))

    merged = merge(first, second)

    names = {item.method for item in merged.scores if item.corpus == "all"}
    assert names == {"vector:fake", "rerank:a", "rerank:b"}
    assert best(merged.scores, "vector:").mrr_at_10 == 0.6
    assert set(merged.per_query[0].ranks) == {"vector:fake", "rerank:a", "rerank:b"}
    assert [cell.name for cell in merged.cells] == ["fake", "fake-ovh"]
    assert merged.cost_usd == pytest.approx(0.02)
    assert best(merged.scores, "nothing") is None


def test_the_report_names_a_choice_per_setting():
    result = _result(
        {
            "vector:fake": 0.6,
            "vector:fake-ovh": 0.5,
            "fts": 0.3,
            "trigram": 0.2,
            "rerank:cross": 0.7,
            "rerank:llm-nano": 0.9,
        }
    )

    rows = recommendations(result)
    markdown = render(result, "results.json", "gold.json")

    assert rows[0][:2] == ["embedding (openai)", "`fake-embed` @ 8"]
    assert rows[2][:2] == ["lexical search", "`fts`"]
    assert rows[3][:2] == ["reranker", "`cross`"]
    assert "# Benchmark: retrieval" in markdown
    assert "Measured on 04 October 2026" in markdown
    assert "**$0.0100**" in markdown
    assert recommendations(_result({}, cells=())) == []


def test_sections_are_replaced_in_place_appended_or_carried_over():
    first = replace_section("# Report\n", "retrieval", "one")
    second = replace_section(first, "retrieval", "two")
    rewritten = carry_sections(second, "# New report\n")

    assert first == "# Report\n\n" + wrap("retrieval", "one")
    assert sections(second) == {"retrieval": wrap("retrieval", "two")}
    assert rewritten.endswith(wrap("retrieval", "two"))
    assert carry_sections(second, rewritten) == rewritten


async def test_the_command_merges_the_day_and_rewrites_its_section(world_maker, tmp_path, capsys):
    async with world_maker() as session:
        gold_queries = await _queries(session)
    raw = json.loads(RETRIEVAL_GOLD.read_text())
    raw["hadith_collections"] = ["bukhari"]
    raw["queries"] = [
        {
            "id": "q",
            "corpus": "quran",
            "query": "إحياء الأرض",
            "relevant": ["Q:30:50"],
            "source": "t",
        }
    ]
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps(raw))
    report = tmp_path / "BENCHMARK.md"
    report.write_text("# Scenes\n")

    def rerank(request: httpx.Request) -> httpx.Response:
        passages = json.loads(request.content)["passages"]
        return httpx.Response(200, json={"scores": [0.5] * len(passages), "model": "m", "ms": 1})

    nano = EmbeddingClient()
    nano.answers = [lambda call: {"passages": [{"number": 1, "relevance": 8}]}] * 5
    arguments = [
        "--cells", "openai-3-small",
        "--lexical", "fts",
        "--reranker", "cross=http://vision",
        "--llm-rerank", "nano",
        "--gold", str(gold),
        "--results-dir", str(tmp_path / "results"),
        "--report", str(report),
    ]  # fmt: skip
    clients = {AiProvider.OPENAI: nano, AiProvider.OVH: EmbeddingClient(AiProvider.OVH)}
    http = httpx.AsyncClient(transport=httpx.MockTransport(rerank))

    first = await command.run(arguments, sessionmaker=world_maker, clients=clients, http=http)
    second = await command.run(
        arguments,
        sessionmaker=world_maker,
        clients=clients,
        http=httpx.AsyncClient(transport=httpx.MockTransport(rerank)),
    )

    assert (first, second) == (0, 0)
    text = report.read_text()
    assert text.startswith("# Scenes")
    assert text.count("<!-- section:retrieval -->") == 1
    assert "rerank:cross" in text
    saved = json.loads(next((tmp_path / "results").glob("retrieval-*.json")).read_text())
    assert saved["rerank_cell"] == "openai-3-small"
    assert "wrote" in capsys.readouterr().out
    assert gold_queries


async def test_a_reranker_that_does_not_answer_fails_the_command(world_maker, tmp_path, capsys):
    raw = json.loads(RETRIEVAL_GOLD.read_text())
    raw["queries"] = [
        {
            "id": "q",
            "corpus": "quran",
            "query": "إحياء الأرض",
            "relevant": ["Q:30:50"],
            "source": "t",
        }
    ]
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps(raw))
    down = httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(503)))

    code = await command.run(
        [
            "--cells",
            "openai-3-large",
            "--reranker",
            "cross=http://vision",
            "--gold",
            str(gold),
            "--no-report",
            "--results-dir",
            str(tmp_path),
        ],
        sessionmaker=world_maker,
        clients={
            AiProvider.OPENAI: EmbeddingClient(),
            AiProvider.OVH: EmbeddingClient(AiProvider.OVH),
        },
        http=down,
    )

    assert code == 1
    assert "http_503" in capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments",
    [
        ["--cells", "nope"],
        ["--reranker", "no-url"],
        ["--cells", "ovh-bge-m3", "--rerank-cell", "x"],
    ],
)
def test_bad_arguments_are_refused(arguments):
    with pytest.raises(SystemExit):
        command.parse_args(arguments)


async def test_the_command_builds_its_own_clients_and_closes_the_engine(
    monkeypatch, tmp_path, make_settings
):
    made = []

    def client_for(settings, http, *, provider, log):
        made.append(provider)
        return EmbeddingClient(provider)

    async def no_gold(_session, _gold):
        raise command.RerankerDownError("stop here")

    disposed = []

    async def dispose() -> None:
        disposed.append(True)

    monkeypatch.setattr(command, "client_for", client_for)
    monkeypatch.setattr(command, "resolve_gold", no_gold)
    monkeypatch.setattr(command, "dispose_engine", dispose)
    monkeypatch.setattr(command, "load_concept_index", _empty_index)

    code = await command.run(["--no-report"], settings=make_settings())

    assert code == 1
    assert set(made) == set(AiProvider)
    assert disposed == [True]


async def _empty_index(_session, corpus, **_kwargs):
    from src.retrieval.concepts import ConceptIndex

    return ConceptIndex(corpus, {})


def test_a_rerank_cell_can_be_named_and_the_report_left_alone(tmp_path):
    args = command.parse_args(
        [
            "--cells",
            "ovh-bge-m3",
            "--rerank-cell",
            "ovh-bge-m3",
            "--no-report",
            "--results-dir",
            str(tmp_path),
        ]
    )

    written = command.write_outputs(_result({"fts": 0.3}), args)

    assert args.rerank_cell == "ovh-bge-m3"
    assert [path.name for path in written] == ["retrieval-2026-10-04.json"]


def test_main_runs_the_command(monkeypatch):
    async def fake(argv):
        return 3

    monkeypatch.setattr(command, "run", fake)

    assert command.main([]) == 3


def test_paths_outside_the_repository_are_written_in_full():
    assert command._relative(Path("/elsewhere/x.json")) == "/elsewhere/x.json"
