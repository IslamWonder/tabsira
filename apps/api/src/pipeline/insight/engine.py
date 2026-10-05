"""
PipelineInsightEngine: the `InsightEngine` of `src.pipeline.engine`, stage by stage.

UNDERSTANDING   the ontology resolves the scene and applies its constraints (a
                block stops a scan focused on it; a question waits for its
                answer); the store is checked to hold a searchable corpus; the
                intent planner turns the scene into search intents, each with
                its clues, its observable meaning, the concept to test and its
                queries. No insight is decided here and no learner data is read.
SEARCHING       per intent and per corpus (the Quran and the hadiths stay
                apart): lexical lists (full text, concepts) and semantic lists
                (vectors), fused by RRF with one weight per channel, then the
                reranker when one is on, reading the intent's own sentence.
VERIFYING       the relevance verifier tests every shortlisted text against
                its intent, one call per intent, all at once, and names the
                pair that serves one meaning; the gate applies eligibility
                (decisions 18 and 58: an unruled hadith waits, the verse shows
                alone), pairs on its own only when the verifier named no pair
                and then within one tier, and prefers a text the learner has
                not seen. When
                no intent reached a complete pair, the intents that found no
                accepted text go back to the planner with the rejection
                reasons: two refinement rounds at most, same clues, same
                meaning, other words.
COMPOSING       the server chooses the learning unit and orders what passed
                (focus, complete pair, relation, next step, new texts); the
                composer writes the explanation from the confirmed intent and
                the verifier's links, one call per insight, all at once;
                scripture never leaves the store through it.

The result says what happened: `needs_clarification` with one question,
`no_relevant_evidence` when the searches ran and nothing passed (abstaining is
a correct result), `incomplete_evidence_pair` when the only fitting hadith
waits for a ruling and no verse stands beside it, `corpus_unavailable` when
the store holds no vectors of the configured model, `retrieval_error` when
the query embedding failed, `model_unavailable` when a model call failed or
kept writing scripture-like text, `source_unavailable` when the database did
not answer. Every stage reports itself through `on_stage` and records its
time in `stage_ms`; the whole run is written to `trace`: ids, ranks, reasons
and the planner's guarded words about the scene (concepts, queries); never a
stored text, never the learner.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ai.client import ModelClient, client_for
from src.ai.errors import AiCallError
from src.ai.records import CallLog
from src.config import RerankerKind, Settings
from src.models import EmbeddedCorpus
from src.pipeline.engine import (
    EngineRequest,
    EngineResult,
    EngineStage,
    EngineStatus,
    HadithRef,
    ProgressCallback,
)
from src.pipeline.insight.composer import Composable, InsightComposer
from src.pipeline.insight.context import SceneContext, build_context
from src.pipeline.insight.evidence import (
    NOT_SEARCHED,
    NOTHING_FOUND,
    EvidenceRelevanceVerifier,
    GateResult,
    Shortlist,
    gate,
    seen_ids,
    shortlist_of,
)
from src.pipeline.insight.guard import quran_detector, scripture_guard
from src.pipeline.insight.intents import (
    FailedIntent,
    IntentPlan,
    PlannerLeakError,
    SearchIntent,
    SemanticIntentPlanner,
)
from src.pipeline.insight.learning import (
    LearningPath,
    RankedInsight,
    domain_counts,
    load_path,
    rank_key,
    unit_for,
)
from src.pipeline.insight.search import (
    VERIFY_TOP,
    Embedding,
    EvidenceSearch,
    Found,
    SearchResult,
    embed_queries,
    rerank_query,
)
from src.pipeline.leak_guard import LeakDetector
from src.pipeline.schemas import SceneAnalysis
from src.retrieval.concepts import ConceptIndex, load_concept_index
from src.retrieval.reranker import LlmReranker, Reranker, RerankerClient
from src.retrieval.vector import has_vectors
from src.services.ontology_candidates import (
    SOURCE_PLANNER,
    SOURCE_VISION_MODEL,
    record_unknown_concepts,
    record_unresolved,
)

log = logging.getLogger("tabsira.pipeline.engine")

REFINEMENT_ROUNDS = 2
TRACE_VERSION = 1


@dataclass(frozen=True, slots=True)
class Resources:
    """What every scan reads and no scan changes."""

    concepts: dict[EmbeddedCorpus, ConceptIndex]
    quran: LeakDetector
    path: LearningPath | None
    # Whether the store holds vectors of the configured embedding model, per corpus.
    vectors: dict[EmbeddedCorpus, bool]

    @property
    def searchable(self) -> bool:
        """A corpus is searchable when its concepts or its vectors are there to search."""
        return all(
            len(self.concepts[corpus]) > 0 or self.vectors.get(corpus, False)
            for corpus in EmbeddedCorpus
        )


class ResourceCache:
    """Loads the resources once and shares them between engines (one per process)."""

    def __init__(self) -> None:
        self._resources: Resources | None = None
        self._lock = asyncio.Lock()

    async def get(self, session: AsyncSession, embedding: Embedding | None = None) -> Resources:
        """Load the concept indexes, the Quran shingles, the learning path and the vector check, once."""
        async with self._lock:
            if self._resources is None:
                vectors = {
                    corpus: (
                        await has_vectors(
                            session,
                            corpus,
                            model=embedding.model,
                            dimensions=embedding.dimensions,
                        )
                        if embedding is not None
                        else False
                    )
                    for corpus in EmbeddedCorpus
                }
                self._resources = Resources(
                    concepts={
                        corpus: await load_concept_index(session, corpus)
                        for corpus in EmbeddedCorpus
                    },
                    quran=await quran_detector(session),
                    path=await load_path(session),
                    vectors=vectors,
                )
            return self._resources


class _Stopped(Exception):  # noqa: N818 - an early answer with a status, not a fault
    """An early answer: the scan stops here with this status."""

    def __init__(self, status: EngineStatus, question: str | None = None) -> None:
        super().__init__(status.value)
        self.status = status
        self.question = question


class _Clock:
    """Times the stages and tells the caller when each one starts."""

    def __init__(self, on_stage: ProgressCallback | None, clock: Callable[[], float]) -> None:
        self._on_stage = on_stage
        self._clock = clock
        self.stage_ms: dict[EngineStage, int] = {}
        self._current: EngineStage | None = None
        self._started = 0.0

    async def enter(self, stage: EngineStage) -> None:
        self.stop()
        self._current, self._started = stage, self._clock()
        if self._on_stage is not None:
            await self._on_stage(stage)

    def stop(self) -> None:
        if self._current is not None:
            spent = round((self._clock() - self._started) * 1000)
            self.stage_ms[self._current] = self.stage_ms.get(self._current, 0) + spent
            self._current = None


def visible_clues(scene: SceneAnalysis, intent: SearchIntent) -> tuple[str, ...]:
    """Return the scene's own words for the clues an intent rests on: its entities and actions."""
    entities = {entity.id: entity.label_arabic for entity in scene.entities}
    actions = {action.id: action.label for action in scene.actions}
    clues = [entities[e] for e in intent.entity_ids if entities.get(e)]
    clues += [actions[a] for a in intent.action_ids if actions.get(a)]
    return tuple(dict.fromkeys(clues))


def unit_texts(scene: SceneAnalysis, intent: SearchIntent) -> list[str]:
    """Return the words a learning unit is matched against: the confirmed intent and the scene."""
    return [
        intent.candidate_concept,
        intent.observable_meaning,
        intent.relation_description or "",
        scene.description,
    ]


class PipelineInsightEngine:
    """Plans, searches, verifies and composes insights for one analysed scene."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        client: ModelClient,
        *,
        embedding: Embedding | None,
        reranker: Reranker | None,
        refinement_rounds: int = REFINEMENT_ROUNDS,
        resources: ResourceCache | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._client = client
        self._embedding = embedding
        self._reranker = reranker
        self._rounds = refinement_rounds
        self._clock = clock
        self._planner = SemanticIntentPlanner(client)
        self._verifier = EvidenceRelevanceVerifier(client)
        self._composer = InsightComposer(client)
        self._resources = resources or ResourceCache()

    async def propose(
        self, request: EngineRequest, on_stage: ProgressCallback | None = None
    ) -> EngineResult:
        clock = _Clock(on_stage, self._clock)
        awaiting: list[HadithRef] = []
        trace: dict[str, Any] = {"version": TRACE_VERSION, "scan_id": request.scan_id}
        try:
            async with self._sessionmaker() as session:
                try:
                    return await self._propose(session, request, clock, awaiting, trace)
                except _Stopped as stopped:
                    await session.commit()
                    clock.stop()
                    trace["status"] = stopped.status.value
                    return EngineResult(
                        status=stopped.status,
                        clarification_question=stopped.question,
                        awaiting_ruling=awaiting,
                        stage_ms=clock.stage_ms,
                        trace=trace,
                    )
        except (AiCallError, PlannerLeakError) as error:
            log.warning("insight engine stopped by a model: %s", error)
            status = EngineStatus.MODEL_UNAVAILABLE
        except (SQLAlchemyError, OSError) as error:
            log.warning("insight engine stopped by the store: %s", type(error).__name__)
            status = EngineStatus.SOURCE_UNAVAILABLE
        clock.stop()
        trace["status"] = status.value
        return EngineResult(status=status, stage_ms=clock.stage_ms, trace=trace)

    async def _propose(
        self,
        session: AsyncSession,
        request: EngineRequest,
        clock: _Clock,
        awaiting: list[HadithRef],
        trace: dict[str, Any],
    ) -> EngineResult:
        await clock.enter(EngineStage.UNDERSTANDING)
        context, plan, resources = await self._understand(session, request, trace)
        passed = await self._find_evidence(
            session, request, context, plan, resources, clock, awaiting, trace
        )
        ranked = self._ranked(request, passed, resources.path)
        await session.commit()
        await clock.enter(EngineStage.COMPOSING)
        hadith_texts = [
            item.result.hadith.found.document.text
            for item in ranked
            if item.result.hadith is not None
        ]
        composition = await self._composer.compose(
            request.scene,
            ranked,
            request.learner,
            scripture_guard(resources.quran, hadith_texts, session),
            resources.path.version if resources.path else None,
        )
        clock.stop()
        trace["chosen"] = [
            {
                "intent_id": item.result.intent.intent_id,
                "quran": item.result.quran_ref.model_dump(exclude={"kind"})
                if item.result.quran_ref
                else None,
                "hadith": item.result.hadith_ref.model_dump(exclude={"kind"})
                if item.result.hadith_ref
                else None,
                "relation": item.result.relation.value,
                "unit": item.unit.unit.unit_id if item.unit else None,
            }
            for item in ranked
        ]
        trace["composer"] = {"prompt": composition.prompt_version, "leaked": composition.leaked}
        if not composition.insights:
            trace["status"] = EngineStatus.MODEL_UNAVAILABLE.value
            return EngineResult(
                status=EngineStatus.MODEL_UNAVAILABLE,
                awaiting_ruling=awaiting,
                stage_ms=clock.stage_ms,
                trace=trace,
            )
        trace["status"] = EngineStatus.OK.value
        return EngineResult(
            status=EngineStatus.OK,
            insights=composition.insights,
            awaiting_ruling=awaiting,
            stage_ms=clock.stage_ms,
            trace=trace,
        )

    async def _understand(
        self, session: AsyncSession, request: EngineRequest, trace: dict[str, Any]
    ) -> tuple[SceneContext, IntentPlan, Resources]:
        scene = request.scene
        context = await build_context(
            session, scene, clarified=request.clarification_answer is not None
        )
        focus = request.focus_entity_id
        if focus is not None and focus in context.blocked:
            raise _Stopped(EngineStatus.NO_RELEVANT_EVIDENCE)
        if focus is not None and focus in context.to_clarify:
            raise _Stopped(EngineStatus.NEEDS_CLARIFICATION, context.question_for([focus]))
        resources = await self._resources.get(session, self._embedding)
        trace["corpus"] = {
            "vectors": {corpus.value: ready for corpus, ready in resources.vectors.items()},
            "concepts": {corpus.value: len(index) for corpus, index in resources.concepts.items()},
        }
        if not resources.searchable:
            log.warning("no searchable corpus: %s", trace["corpus"])
            raise _Stopped(EngineStatus.CORPUS_UNAVAILABLE)
        plan = await self._planner.plan(
            request, context, scripture_guard(resources.quran, session=session)
        )
        trace["plan"] = {
            "prompt": plan.prompt_version,
            "intents": [intent.as_trace() for intent in plan.intents],
            "dropped": list(plan.dropped),
        }
        example = None if scene.is_sensitive else scene.description
        await record_unresolved(
            session, context.unresolved, source=SOURCE_VISION_MODEL, example=example
        )
        await record_unknown_concepts(
            session, plan.unknown_concepts, source=SOURCE_PLANNER, example=example
        )
        if not plan.intents:
            question = plan.question or context.question_for(plan.waiting_on)
            if question is None and request.clarification_answer is None:
                question = scene.clarification_question
            # The scene's question was written by the vision model: it meets the store too.
            if question and await scripture_guard(resources.quran, session=session).leaks(
                [question]
            ):
                question = None
            if question:
                raise _Stopped(EngineStatus.NEEDS_CLARIFICATION, question)
            raise _Stopped(EngineStatus.NO_RELEVANT_EVIDENCE)
        return context, plan, resources

    async def _find_evidence(
        self,
        session: AsyncSession,
        request: EngineRequest,
        context: SceneContext,
        plan: IntentPlan,
        resources: Resources,
        clock: _Clock,
        awaiting: list[HadithRef],
        trace: dict[str, Any],
    ) -> list[GateResult]:
        search = EvidenceSearch(
            embedding=self._embedding, reranker=self._reranker, concepts=resources.concepts
        )
        seen_verses, seen_hadiths = await seen_ids(session, request.learner)
        pending = plan.intents
        passed: list[GateResult] = []
        rounds: list[dict[str, Any]] = []
        trace["rounds"] = rounds
        refinements = 0
        leaked = False
        while True:
            await clock.enter(EngineStage.SEARCHING)
            shortlists, searched = await self._shortlists(session, search, pending)
            await clock.enter(EngineStage.VERIFYING)
            texts = [found.document.text for item in shortlists for found in item.hadith]
            verdicts = await self._verifier.verify(
                request.scene, shortlists, scripture_guard(resources.quran, texts, session)
            )
            leaked = leaked or any(verdict is None for verdict in verdicts.values())
            failed: list[FailedIntent] = []
            gated: list[dict[str, Any]] = []
            for index, shortlist in enumerate(shortlists):
                result = await gate(
                    session,
                    shortlist,
                    verdicts.get(index),
                    seen_verses=seen_verses,
                    seen_hadiths=seen_hadiths,
                )
                awaiting += [ref for ref in result.awaiting if ref not in awaiting]
                gated.append({**searched[index], "gate": result.as_trace()})
                if result.passed:
                    passed.append(result)
                else:
                    failed.append(FailedIntent(result.intent, result.reasons()))
            rounds.append({"round": refinements, "intents": gated})
            complete = any(result.pair_complete for result in passed)
            if complete or not failed or refinements == self._rounds:
                break
            refinements += 1
            await clock.enter(EngineStage.SEARCHING)
            retry = await self._planner.plan(
                request,
                context,
                scripture_guard(resources.quran, session=session),
                refine=failed,
                id_prefix=f"r{refinements}i",
            )
            pending = retry.intents
            if not pending:
                rounds.append({"round": refinements, "intents": [], "dropped": retry.dropped})
                break
        if not passed:
            # Evidence was found and accepted, but the only fitting hadith waits for a ruling:
            # that is not «no text fits», and the reader is told so.
            if awaiting:
                raise _Stopped(EngineStatus.INCOMPLETE_EVIDENCE_PAIR)
            # A verifier that kept writing scripture-like text left an intent unjudged: a model
            # fault, never «no text fits».
            if leaked:
                raise _Stopped(EngineStatus.MODEL_UNAVAILABLE)
            raise _Stopped(EngineStatus.NO_RELEVANT_EVIDENCE)
        return passed

    async def _shortlists(
        self, session: AsyncSession, search: EvidenceSearch, intents: Sequence[SearchIntent]
    ) -> tuple[list[Shortlist], list[dict[str, Any]]]:
        """Search every intent's corpora, rerank all the lists at once, and say what was found."""
        sentences = [
            query
            for intent in intents
            for corpus in EmbeddedCorpus
            for query in intent.queries_of(corpus).semantic
        ]
        vectors, embed_error = await embed_queries(self._embedding, sentences)
        if embed_error:
            # A search without its semantic half is not the search that was planned: the
            # scan says so instead of answering from the lexical half alone.
            log.warning("query embedding failed: %s; the search was not run", embed_error)
            raise _Stopped(EngineStatus.RETRIEVAL_ERROR)
        # A session reads one query at a time, so the lists are searched in turn; the
        # reranker calls do not touch it and run together: one wait, not one per list.
        pending: list[tuple[str, list[Found]]] = []
        notes: list[str | None] = []
        for intent in intents:
            for corpus in EmbeddedCorpus:
                queries = intent.queries_of(corpus)
                found: list[Found] = []
                note: str | None = NOT_SEARCHED
                if not queries.empty:
                    found = await search.search(session, corpus, queries, vectors)
                    note = NOTHING_FOUND if not found else None
                pending.append((rerank_query(queries, intent.observable_meaning), found))
                notes.append(note)
        results: list[SearchResult] = await asyncio.gather(
            *(search.rerank(query, found) for query, found in pending)
        )
        shortlists: list[Shortlist] = []
        traced: list[dict[str, Any]] = []
        for index, intent in enumerate(intents):
            quran, hadith = results[2 * index], results[2 * index + 1]
            quran_note, hadith_note = notes[2 * index], notes[2 * index + 1]
            shortlists.append(
                shortlist_of(
                    intent,
                    quran.found,
                    hadith.found,
                    quran_note=quran_note,
                    hadith_note=hadith_note,
                )
            )
            traced.append(
                {
                    "intent_id": intent.intent_id,
                    EmbeddedCorpus.QURAN.value: _searched_trace(quran, quran_note, self._reranker),
                    EmbeddedCorpus.HADITH.value: _searched_trace(
                        hadith, hadith_note, self._reranker
                    ),
                }
            )
        return shortlists, traced

    @staticmethod
    def _ranked(
        request: EngineRequest, passed: list[GateResult], path: LearningPath | None
    ) -> list[Composable]:
        """Order what passed by masar §10.4 and v2 §11, and keep one insight per pair of texts."""
        scene = request.scene
        domains = domain_counts(path, request.learner) if path else {}
        items = [
            Composable(
                result=result,
                unit=unit_for(path, unit_texts(scene, result.intent), request.learner),
                visible_clues=visible_clues(scene, result.intent),
            )
            for result in passed
        ]

        def key(item: Composable) -> tuple[int, ...]:
            result, unit = item.result, item.unit
            chosen = [c for c in (result.quran, result.hadith) if c is not None]
            return rank_key(
                RankedInsight(
                    on_focus=request.focus_entity_id in result.intent.entity_ids,
                    pair_complete=result.pair_complete,
                    relation=result.relation,
                    unit=unit,
                    new_texts=sum(1 for c in chosen if not c.review),
                    domain_seen=domains.get(unit.unit.domain_id, 0) if unit else 0,
                )
            )

        kept: list[Composable] = []
        pairs: set[tuple[object, object]] = set()
        for item in sorted(items, key=key):
            pair = (item.result.quran_ref, item.result.hadith_ref)
            if pair not in pairs:
                pairs.add(pair)
                kept.append(item)
        # v2 §11: a lone text is shown only when no intent reached a complete pair; it never
        # sits beside a complete one.
        complete = [item for item in kept if item.result.pair_complete]
        return (complete or kept[:1])[: request.max_insights]


def _searched_trace(
    result: SearchResult, note: str | None, reranker: Reranker | None
) -> dict[str, Any]:
    if reranker is None:
        rerank = "off"
    elif result.rerank_error:
        rerank = f"skipped: {result.rerank_error}"
    else:
        rerank = f"ok: {result.rerank_model or 'reranker'} in {result.rerank_ms} ms"
    return {
        "note": note,
        "found": len(result.found),
        "rerank": rerank,
        "shortlist": [found.as_trace() for found in result.found[:VERIFY_TOP]],
    }


# One per process: every engine the factory builds shares the indexes and the shingles.
SHARED_RESOURCES = ResourceCache()


def build_engine(
    settings: Settings,
    http: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    client: ModelClient | None = None,
    log: CallLog | None = None,
    resources: ResourceCache | None = None,
) -> PipelineInsightEngine:
    """
    Build the engine of the active provider: its models, its embedding and the reranker.

    This is the factory the scan workflow registers for the pipeline engine. It is
    cheap to call per scan: the concept indexes, the Quran shingles and the learning
    path are loaded once per process (`SHARED_RESOURCES`). A scan passes its own
    `client`, so every call of the engine is recorded with the scan's; without one
    the engine gets a client of the active provider, recording into `log`.
    """
    client = client or client_for(settings, http, log=log)
    block = settings.ai
    embedding = (
        Embedding(client, block.embedding_model, block.embedding_dimensions)
        if block.embedding_model
        else None
    )
    return PipelineInsightEngine(
        sessionmaker,
        client,
        embedding=embedding,
        reranker=build_reranker(settings, http, client),
        resources=resources or SHARED_RESOURCES,
    )


def active_reranker(settings: Settings) -> RerankerKind:
    """Return the reranker that runs: the one RERANKER names, or OFF when it has nothing to call."""
    if settings.reranker is RerankerKind.LLM and not settings.ai.rerank_model:
        return RerankerKind.OFF
    if settings.reranker is RerankerKind.CROSS_ENCODER and not settings.reranker_url:
        return RerankerKind.OFF
    return settings.reranker


def build_reranker(
    settings: Settings, http: httpx.AsyncClient, client: ModelClient
) -> Reranker | None:
    """Return the active reranker, or None when reranking is off."""
    timeout = settings.reranker_timeout_seconds
    kind = active_reranker(settings)
    if kind is RerankerKind.LLM:
        return LlmReranker(client, model=settings.ai.rerank_model, timeout_seconds=timeout)
    if kind is RerankerKind.CROSS_ENCODER:
        return RerankerClient(settings.reranker_url, http, timeout_seconds=timeout)
    return None
