"""
PipelineInsightEngine: the `InsightEngine` of `src.pipeline.engine`, stage by stage.

UNDERSTANDING   the ontology resolves the scene and applies its constraints (a
                block stops a scan focused on it; a question waits for its
                answer); the learning path offers the units that fit; the
                planner proposes up to three candidates with concept queries.
SEARCHING       hybrid search, Quran and hadith apart, then the reranker
                (decision 41) over every list at once.
VERIFYING       the verifier judges every shortlisted text; the gate keeps the
                eligible and relevant ones (decision 18 for hadith), queues a
                wanted hadith without a ruling, prefers a text the learner has
                not seen at equal strength. A candidate with no evidence goes
                back to the planner with what failed: two refinement rounds
                at most, then it is dropped.
COMPOSING       the composer writes the explanation; scripture never leaves the
                store through it.

The result is honest about what happened: `needs_clarification` with one
question, `no_relevant_evidence` when nothing passed the gate (abstaining is a
correct result), `model_unavailable` when a model call failed or kept writing
scripture-like text, `source_unavailable` when the database did not answer.
Every stage reports itself through `on_stage` as it starts and records its
time in `stage_ms`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

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
from src.pipeline.insight.composer import InsightComposer
from src.pipeline.insight.context import SceneContext, build_context
from src.pipeline.insight.evidence import (
    GateResult,
    Shortlist,
    VerifierLeakError,
    gate,
    seen_ids,
    shortlist_of,
    verify,
)
from src.pipeline.insight.guard import quran_detector, scripture_guard
from src.pipeline.insight.learning import (
    LearningPath,
    RankedInsight,
    UnitOption,
    domain_counts,
    load_path,
    rank_key,
    unit_options,
)
from src.pipeline.insight.planner import (
    FailedSearch,
    InsightPlanner,
    Plan,
    PlannedCandidate,
    PlannerLeakError,
)
from src.pipeline.insight.search import Embedding, EvidenceSearch, Found, embed_queries
from src.pipeline.leak_guard import LeakDetector
from src.retrieval.concepts import ConceptIndex, load_concept_index
from src.retrieval.refs import Numbering, is_quran, resolve_hadiths, resolve_verses
from src.retrieval.reranker import LlmReranker, Reranker, RerankerClient
from src.services.ontology_candidates import (
    SOURCE_PLANNER,
    SOURCE_VISION_MODEL,
    record_unknown_concepts,
    record_unresolved,
)

log = logging.getLogger("tabsira.pipeline.engine")

REFINEMENT_ROUNDS = 2


@dataclass(frozen=True, slots=True)
class Resources:
    """What every scan reads and no scan changes."""

    concepts: dict[EmbeddedCorpus, ConceptIndex]
    quran: LeakDetector
    path: LearningPath | None


class ResourceCache:
    """Loads the resources once and shares them between engines (one per process)."""

    def __init__(self) -> None:
        self._resources: Resources | None = None
        self._lock = asyncio.Lock()

    async def get(self, session: AsyncSession) -> Resources:
        """Load the concept indexes, the Quran shingles and the learning path, once."""
        async with self._lock:
            if self._resources is None:
                self._resources = Resources(
                    concepts={
                        corpus: await load_concept_index(session, corpus)
                        for corpus in EmbeddedCorpus
                    },
                    quran=await quran_detector(session),
                    path=await load_path(session),
                )
            return self._resources


class _Stopped(Exception):  # noqa: N818 - an early, successful answer, not an error
    """An early answer: the scan stops here with this result."""

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


def scene_texts(request: EngineRequest, context: SceneContext) -> list[str]:
    """Return the words the learning path is matched against: what the scene shows."""
    scene = request.scene
    texts = [scene.description, *(a.label for a in scene.actions)]
    texts += [concept for item in context.entities.values() for concept in item.concepts()]
    if request.clarification_answer:
        texts.append(request.clarification_answer)
    return texts


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
        self._planner = InsightPlanner(client)
        self._composer = InsightComposer(client)
        self._resources = resources or ResourceCache()

    async def propose(
        self, request: EngineRequest, on_stage: ProgressCallback | None = None
    ) -> EngineResult:
        clock = _Clock(on_stage, self._clock)
        awaiting: list[HadithRef] = []
        try:
            async with self._sessionmaker() as session:
                try:
                    return await self._propose(session, request, clock, awaiting)
                except _Stopped as stopped:
                    await session.commit()
                    clock.stop()
                    return EngineResult(
                        status=stopped.status,
                        clarification_question=stopped.question,
                        awaiting_ruling=awaiting,
                        stage_ms=clock.stage_ms,
                    )
        except (AiCallError, PlannerLeakError, VerifierLeakError) as error:
            log.warning("insight engine stopped by a model: %s", error)
            status = EngineStatus.MODEL_UNAVAILABLE
        except (SQLAlchemyError, OSError) as error:
            log.warning("insight engine stopped by the store: %s", type(error).__name__)
            status = EngineStatus.SOURCE_UNAVAILABLE
        clock.stop()
        return EngineResult(status=status, stage_ms=clock.stage_ms)

    async def _propose(
        self,
        session: AsyncSession,
        request: EngineRequest,
        clock: _Clock,
        awaiting: list[HadithRef],
    ) -> EngineResult:
        await clock.enter(EngineStage.UNDERSTANDING)
        context, plan, options, resources = await self._understand(session, request)
        passed = await self._find_evidence(
            session, request, context, plan, options, resources, clock, awaiting
        )
        ranked = self._ranked(request, passed, resources.path)
        await session.commit()
        await clock.enter(EngineStage.COMPOSING)
        hadith_texts = [r.hadith.found.document.text for r in ranked if r.hadith is not None]
        composition = await self._composer.compose(
            request.scene,
            ranked,
            request.learner,
            scripture_guard(resources.quran, hadith_texts),
            resources.path.version if resources.path else None,
        )
        clock.stop()
        if not composition.insights:
            return EngineResult(
                status=EngineStatus.MODEL_UNAVAILABLE,
                awaiting_ruling=awaiting,
                stage_ms=clock.stage_ms,
            )
        return EngineResult(
            status=EngineStatus.OK,
            insights=composition.insights,
            awaiting_ruling=awaiting,
            stage_ms=clock.stage_ms,
        )

    async def _understand(
        self, session: AsyncSession, request: EngineRequest
    ) -> tuple[SceneContext, Plan, list[UnitOption], Resources]:
        scene = request.scene
        context = await build_context(
            session, scene, clarified=request.clarification_answer is not None
        )
        focus = request.focus_entity_id
        if focus is not None and focus in context.blocked:
            raise _Stopped(EngineStatus.NO_RELEVANT_EVIDENCE)
        if focus is not None and focus in context.to_clarify:
            raise _Stopped(EngineStatus.NEEDS_CLARIFICATION, context.question_for([focus]))
        resources = await self._resources.get(session)
        options = (
            unit_options(resources.path, scene_texts(request, context), request.learner)
            if resources.path
            else []
        )
        plan = await self._planner.plan(request, context, options, scripture_guard(resources.quran))
        example = None if scene.is_sensitive else scene.description
        await record_unresolved(
            session, context.unresolved, source=SOURCE_VISION_MODEL, example=example
        )
        await record_unknown_concepts(
            session, plan.unknown_concepts, source=SOURCE_PLANNER, example=example
        )
        if not plan.candidates:
            question = plan.question or context.question_for(plan.waiting_on)
            if question is None and request.clarification_answer is None:
                question = scene.clarification_question
            # The scene's question was written by the vision model: it meets the Quran too.
            if question and scripture_guard(resources.quran).check(question).leaked:
                question = None
            if question:
                raise _Stopped(EngineStatus.NEEDS_CLARIFICATION, question)
            raise _Stopped(EngineStatus.NO_RELEVANT_EVIDENCE)
        return context, plan, options, resources

    async def _find_evidence(
        self,
        session: AsyncSession,
        request: EngineRequest,
        context: SceneContext,
        plan: Plan,
        options: list[UnitOption],
        resources: Resources,
        clock: _Clock,
        awaiting: list[HadithRef],
    ) -> list[GateResult]:
        search = EvidenceSearch(
            embedding=self._embedding, reranker=self._reranker, concepts=resources.concepts
        )
        seen_verses, seen_hadiths = await seen_ids(session, request.learner)
        pending = plan.candidates
        passed: list[GateResult] = []
        refinements = 0
        while True:
            await clock.enter(EngineStage.SEARCHING)
            shortlists = await self._shortlists(session, search, pending)
            await clock.enter(EngineStage.VERIFYING)
            texts = [found.document.text for item in shortlists for found in item.hadith]
            verdicts = await verify(
                self._client, request.scene, shortlists, scripture_guard(resources.quran, texts)
            )
            failed: list[PlannedCandidate] = []
            for index, shortlist in enumerate(shortlists):
                result = await gate(
                    session,
                    shortlist,
                    verdicts.get(index, {}),
                    seen_verses=seen_verses,
                    seen_hadiths=seen_hadiths,
                )
                awaiting += [ref for ref in result.awaiting if ref not in awaiting]
                if result.passed:
                    passed.append(result)
                else:
                    failed.append(shortlist.candidate)
            if not failed or refinements == self._rounds:
                break
            refinements += 1
            await clock.enter(EngineStage.SEARCHING)
            retry = await self._planner.plan(
                request,
                context,
                options,
                scripture_guard(resources.quran),
                refine=[
                    FailedSearch(c.concept, c.relation, c.quran_queries + c.hadith_queries)
                    for c in failed
                ],
            )
            pending = retry.candidates[: len(failed)]
            if not pending:
                break
        if not passed:
            raise _Stopped(EngineStatus.NO_RELEVANT_EVIDENCE)
        return passed

    async def _shortlists(
        self, session: AsyncSession, search: EvidenceSearch, candidates: Sequence[PlannedCandidate]
    ) -> list[Shortlist]:
        queries = [q for c in candidates for q in (*c.quran_queries, *c.hadith_queries)]
        vectors, embed_error = await embed_queries(self._embedding, queries)
        if embed_error:
            log.warning("query embedding skipped: %s; searching without vectors", embed_error)
        # A session reads one query at a time, so the lists are searched in turn; the
        # reranker calls do not touch it and run together: one wait, not one per list.
        searched: list[tuple[Sequence[str], list[Found]]] = []
        for candidate in candidates:
            verse_anchors, hadith_anchors = await self._anchors(session, candidate)
            for corpus, corpus_queries, anchors in (
                (EmbeddedCorpus.QURAN, candidate.quran_queries, verse_anchors),
                (EmbeddedCorpus.HADITH, candidate.hadith_queries, hadith_anchors),
            ):
                # A corpus the planner asked nothing of is not searched: no half is filled
                # with a text found by the other half's queries.
                found = (
                    await search.search(session, corpus, corpus_queries, vectors, anchors=anchors)
                    if corpus_queries
                    else []
                )
                searched.append((corpus_queries, found))
        results = await asyncio.gather(*(search.rerank(q, found) for q, found in searched))
        for result in results:
            if result.rerank_error:
                log.warning("reranker skipped: %s; fused order kept", result.rerank_error)
        return [
            shortlist_of(candidate, results[2 * index].found, results[2 * index + 1].found)
            for index, candidate in enumerate(candidates)
        ]

    @staticmethod
    async def _anchors(
        session: AsyncSession, candidate: PlannedCandidate
    ) -> tuple[list[int], list[int]]:
        """Return the verse and hadith ids of the chosen unit's anchors («مراجع الارتكاز»)."""
        if candidate.unit is None:
            return [], []
        anchors = candidate.unit.unit.anchors
        verses = await resolve_verses(session, [a for a in anchors if is_quran(a)])
        hadiths = await resolve_hadiths(
            session, [a for a in anchors if not is_quran(a)], Numbering.SUNNAH_COM
        )
        return (
            [key for ids in verses.values() for key in ids],
            [key for ids in hadiths.values() for key in ids],
        )

    @staticmethod
    def _ranked(
        request: EngineRequest, passed: list[GateResult], path: LearningPath | None
    ) -> list[GateResult]:
        """Order what passed by masar §10.4 and keep one insight per pair of texts."""
        domains = domain_counts(path, request.learner) if path else {}

        def key(result: GateResult) -> tuple[int, ...]:
            chosen = [c for c in (result.quran, result.hadith) if c is not None]
            unit = result.candidate.unit
            return rank_key(
                RankedInsight(
                    on_focus=request.focus_entity_id in result.candidate.entity_ids,
                    relation=result.relation,
                    unit=unit,
                    new_texts=sum(1 for c in chosen if not c.review),
                    domain_seen=domains.get(unit.unit.domain_id, 0) if unit else 0,
                )
            )

        kept: list[GateResult] = []
        pairs: set[tuple[object, object]] = set()
        for result in sorted(passed, key=key):
            pair = (result.quran_ref, result.hadith_ref)
            if pair not in pairs:
                pairs.add(pair)
                kept.append(result)
        return kept[: request.max_insights]


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
    match active_reranker(settings):
        case RerankerKind.LLM:
            return LlmReranker(client, model=settings.ai.rerank_model, timeout_seconds=timeout)
        case RerankerKind.CROSS_ENCODER:
            return RerankerClient(settings.reranker_url, http, timeout_seconds=timeout)
        case RerankerKind.OFF:
            return None
