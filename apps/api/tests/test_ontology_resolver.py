"""The ontology resolver on the real thousand entities: layers, scores, reasons, catch-alls and context."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select

from src.models import OntologyEntity
from src.services.ontology_resolver import (
    MAX_CANDIDATES,
    RESOLVED_MIN_SCORE,
    EmbeddingMatch,
    LabelResolution,
    OntologyNotLoadedError,
    OntologyResolver,
    Reason,
    SceneLabel,
    SceneRelation,
    Via,
)

pytestmark = pytest.mark.usefixtures("committed_ontology")


async def resolve_one(session, label, relations=(), **options) -> LabelResolution:
    [resolution] = await OntologyResolver(session, **options).resolve([label], relations)
    return resolution


def ids(resolution: LabelResolution) -> list[str]:
    return [candidate.entity_id for candidate in resolution.candidates]


# ─── Exact label and related objects ───


async def test_an_exact_arabic_label_is_the_first_candidate_with_the_best_score(db_session):
    resolution = await resolve_one(db_session, "هاتف")

    best = resolution.best
    assert (best.entity_id, best.label_ar) == ("E221", "هاتف")
    assert (best.score, best.reason, best.via) == (1.0, Reason.EXACT_LABEL, Via.LABEL)
    assert best.matched == "هاتف"
    assert resolution.resolved is True
    assert best.is_catch_all is False


async def test_the_candidates_are_ranked_and_between_three_and_ten(db_session):
    resolution = await resolve_one(db_session, "هاتف")

    scores = [candidate.score for candidate in resolution.candidates]
    assert 3 <= len(resolution.candidates) <= MAX_CANDIDATES
    assert scores == sorted(scores, reverse=True)
    # An entity that lists the label among its related objects is a neighbour, one place down.
    assert [(c.entity_id, c.reason) for c in resolution.candidates] == [
        ("E221", Reason.EXACT_LABEL),
        ("E227", Reason.RELATED_OBJECT),
        ("E257", Reason.RELATED_OBJECT),
    ]
    assert all(0 < score <= 1 for score in scores)


async def test_a_related_object_scores_lower_the_later_it_sits_in_the_entitys_list(db_session):
    resolution = await resolve_one(db_session, "مطر")

    related = {
        c.entity_id: c.score for c in resolution.candidates if c.reason is Reason.RELATED_OBJECT
    }
    # «ماء» lists «مطر» third: 0.85 less two places of 0.02. «سحابة» lists it first, behind its own label.
    assert related["E021"] == pytest.approx(0.83)
    assert related["E005"] == pytest.approx(0.77)
    assert resolution.best.entity_id == "E006"


async def test_at_most_ten_candidates_whatever_the_ontology_has(db_session):
    resolution = await resolve_one(db_session, "ماء")  # 46 entities list it

    assert len(resolution.candidates) == MAX_CANDIDATES
    assert resolution.best.entity_id == "E021"


async def test_equal_scores_keep_the_order_of_the_ids(db_session):
    resolution = await resolve_one(db_session, "ماء")

    tied = [c.entity_id for c in resolution.candidates if c.score == pytest.approx(0.83)]
    assert tied == sorted(tied, key=lambda entity_id: int(entity_id[1:]))
    assert len(tied) > 1


async def test_the_article_and_the_marks_do_not_matter_but_the_exact_form_scores_higher(db_session):
    plain = await resolve_one(db_session, "سماء")
    with_article = await resolve_one(db_session, "السماء")
    marked = await resolve_one(db_session, "سَمَاءٌ")

    assert (plain.best.entity_id, plain.best.score) == ("E001", 1.0)
    assert (with_article.best.entity_id, with_article.best.score) == ("E001", 0.95)
    assert (marked.best.entity_id, marked.best.score) == ("E001", 1.0)


async def test_an_entity_that_keeps_its_article_is_found_without_it(db_session):
    resolution = await resolve_one(db_session, "كعبة")

    assert (resolution.best.entity_id, resolution.best.label_ar) == ("E298", "الكعبة")
    assert resolution.best.score == 0.95


async def test_a_label_with_the_article_matches_a_related_object_at_a_small_cost(db_session):
    plain = await resolve_one(db_session, "سماء")
    with_article = await resolve_one(db_session, "السماء")

    telescope = {
        resolution.label.text: next(c.score for c in resolution.candidates if c.entity_id == "E638")
        for resolution in (plain, with_article)
    }
    assert telescope["السماء"] == pytest.approx(telescope["سماء"] - 0.03)


# ─── English labels and the Arabic of the vision model ───


async def test_an_english_label_goes_through_its_arabic_hint(db_session):
    resolution = await resolve_one(db_session, "Cell Phone")

    assert (resolution.best.entity_id, resolution.best.via) == ("E221", Via.HINT)
    assert resolution.best.matched == "هاتف"
    assert resolution.resolved is True


async def test_the_arabic_label_of_the_vision_model_is_used_as_it_is(db_session):
    resolution = await resolve_one(db_session, SceneLabel("book", arabic="كتاب"))

    assert (resolution.best.entity_id, resolution.best.via) == ("E181", Via.LABEL)


async def test_both_labels_of_one_thing_give_one_candidate_per_entity(db_session):
    both = await resolve_one(db_session, SceneLabel("cell phone", arabic="هاتف"))

    assert len(ids(both)) == len(set(ids(both)))
    # The Arabic label comes first and keeps the full score.
    assert (both.best.entity_id, both.best.via, both.best.score) == ("E221", Via.LABEL, 1.0)


async def test_a_second_hint_scores_a_little_lower_than_the_first(db_session):
    resolution = await resolve_one(db_session, "dish")  # «صحن تقديم», then «طعام»

    exact = {c.entity_id: c.score for c in resolution.candidates if c.reason is Reason.EXACT_LABEL}
    assert exact == {"E503": 1.0, "E121": pytest.approx(0.9)}
    assert resolution.best.entity_id == "E503"


async def test_a_label_in_the_plural_or_with_an_adjective_finds_its_hint(db_session):
    resolution = await resolve_one(db_session, "old cell phones")

    assert resolution.best.entity_id == "E221"


# ─── A label of several words ───


async def test_a_phrase_that_does_not_resolve_whole_is_tried_one_word_at_a_time(db_session):
    resolution = await resolve_one(db_session, "هاتف ذكي")

    best = resolution.best
    assert (best.entity_id, best.via, best.reason) == ("E221", Via.WORD, Reason.EXACT_LABEL)
    assert best.score == pytest.approx(0.8)
    assert resolution.resolved is True


async def test_a_short_word_of_a_phrase_is_not_tried_alone(db_session):
    # «في» is a particle: it would match half the ontology as a similar text.
    resolution = await resolve_one(db_session, "هاتف في")

    assert resolution.best.entity_id == "E221"
    assert all(c.matched != "في" for c in resolution.candidates)


async def test_a_phrase_that_resolves_whole_is_not_split(db_session):
    resolution = await resolve_one(db_session, "شجرة زيتون")

    assert (resolution.best.entity_id, resolution.best.via, resolution.best.score) == (
        "E044",
        Via.LABEL,
        1.0,
    )


# ─── Similar text ───


async def test_a_text_that_only_looks_like_an_entity_is_a_similar_text_below_every_related_object(
    db_session,
):
    resolution = await resolve_one(db_session, "كرسي")

    similar = [c for c in resolution.candidates if c.reason is Reason.SIMILAR_TEXT]
    assert resolution.best.entity_id == "E147"
    assert {c.entity_id for c in similar} >= {"E095"}  # «كرسي متحرك» contains the word
    assert all(c.score <= 0.65 for c in similar)
    assert all(c.score >= 0.6 * 0.65 for c in similar)


async def test_the_similar_text_layer_uses_the_trigram_index_threshold_and_ignores_noise(
    db_session,
):
    # «هواتف» (phones, a broken plural) shares only a prefix with «هواء»: that is not a likeness.
    resolution = await resolve_one(db_session, "هواتف")

    assert resolution.resolved is False
    assert [c.reason for c in resolution.candidates] == [Reason.CATCH_ALL]


# ─── Catch-alls ───


async def test_a_label_nothing_resolves_gets_the_last_resort_catch_all_alone(db_session):
    resolution = await resolve_one(db_session, "xyzzy")

    assert resolution.resolved is False
    [only] = resolution.candidates
    assert (only.entity_id, only.label_ar) == ("E1000", "موقف غير واضح")
    assert (only.reason, only.score, only.is_catch_all) == (Reason.CATCH_ALL, 0.3, True)
    assert only.special_constraint == "تحديد النوع أو الفعل قبل البحث"


async def test_a_generic_english_label_gets_the_catch_all_of_its_kind(db_session):
    plant = await resolve_one(db_session, "bush")
    insect = await resolve_one(db_session, "unknown bug")
    clothing = await resolve_one(db_session, "some clothing")

    assert [r.best.label_ar for r in (plant, insect, clothing)] == [
        "نبات غير محدد",
        "حشرة غير محددة",
        "لباس غير محدد",
    ]
    assert all(r.resolved is False and r.best.is_catch_all for r in (plant, insect, clothing))


async def test_a_generic_arabic_label_gets_the_catch_all_of_its_kind(db_session):
    resolution = await resolve_one(db_session, "نبتة")

    assert resolution.resolved is False
    assert resolution.best.label_ar == "نبات غير محدد"
    assert resolution.best.reason is Reason.CATCH_ALL
    # The weaker real match comes after it, as an alternative to ask about.
    assert ("E048", Reason.SIMILAR_TEXT) in [(c.entity_id, c.reason) for c in resolution.candidates]


async def test_a_label_that_is_itself_generic_resolves_to_its_catch_all_not_to_neighbours(
    db_session,
):
    resolution = await resolve_one(db_session, "document")

    assert resolution.resolved is False
    assert (resolution.best.entity_id, resolution.best.label_ar) == ("E999", "وثيقة غير محددة")
    # It was an exact match of the hint, so that is what it says; it is not made up.
    assert (resolution.best.reason, resolution.best.score) == (Reason.EXACT_LABEL, 1.0)
    assert len(resolution.candidates) > 1


async def test_a_catch_all_hint_beside_a_specific_one_does_not_hide_the_specific_entity(db_session):
    resolution = await resolve_one(db_session, "plant")

    assert resolution.resolved is True
    assert resolution.best.entity_id == "E041"
    assert not any(c.is_catch_all for c in resolution.candidates)


async def test_the_three_catch_alls_the_spec_names_exist_and_can_be_resolved_to(db_session):
    plants, documents, unclear = await OntologyResolver(db_session).resolve(
        ["نبات غير محدد", "وثيقة غير محددة", "موقف غير واضح"]
    )

    assert [r.best.entity_id for r in (plants, documents, unclear)] == ["E989", "E999", "E1000"]
    assert all(r.best.is_catch_all and not r.resolved for r in (plants, documents, unclear))


@pytest.mark.parametrize("empty", ["", "   ", "،", "\N{ARABIC TATWEEL}\N{ARABIC TATWEEL}"])
async def test_a_label_with_nothing_to_search_is_unresolved_not_an_error(db_session, empty):
    resolution = await resolve_one(db_session, empty)

    assert resolution.resolved is False
    assert resolution.best.entity_id == "E1000"


async def test_without_the_default_catch_all_another_one_is_offered(db_session):
    await db_session.execute(delete(OntologyEntity).where(OntologyEntity.id == "E1000"))

    resolution = await resolve_one(db_session, "xyzzy")

    assert resolution.best.is_catch_all
    assert resolution.best.entity_id == "E999"


async def test_an_ontology_without_any_catch_all_says_so(db_session):
    await db_session.execute(delete(OntologyEntity).where(OntologyEntity.is_catch_all.is_(True)))

    with pytest.raises(OntologyNotLoadedError, match="import it with `make data`"):
        await resolve_one(db_session, "xyzzy")


async def test_an_empty_ontology_says_so(db_session):
    await db_session.execute(delete(OntologyEntity))

    with pytest.raises(OntologyNotLoadedError):
        await resolve_one(db_session, "هاتف")
    assert await db_session.scalar(select(func.count()).select_from(OntologyEntity)) == 0


# ─── Relations ───


async def test_a_relation_brings_up_the_actions_it_names_and_only_reorders(db_session):
    plain = await resolve_one(db_session, "مطر")
    related = await resolve_one(
        db_session, "مطر", [SceneRelation(subject="مطر", predicate="سقي", object="أرض")]
    )

    # The same entities, so a relation never creates or hides a candidate...
    assert set(ids(related)) >= {"E006", "E021", "E039"}
    assert related.best.entity_id == "E006"
    # ...but the ones whose actions the scene shows are activated and rise a little.
    assert related.best.activated == ("سقي",)
    water = next(c for c in related.candidates if c.entity_id == "E021")
    before = next(c for c in plain.candidates if c.entity_id == "E021")
    assert water.activated == ("سقي",)
    assert water.score == pytest.approx(before.score + 0.03)


async def test_without_a_relation_no_action_or_concept_is_active(db_session):
    resolution = await resolve_one(db_session, "مطر")

    assert all(c.activated == () for c in resolution.candidates)


async def test_the_phone_does_not_become_news_unless_the_scene_says_so(db_session):
    quiet = await resolve_one(db_session, "cell phone")
    news = await resolve_one(
        db_session,
        "cell phone",
        [SceneRelation(subject="person", predicate="نقل خبر", object="cell phone")],
    )

    assert quiet.best.activated == ()
    assert news.best.entity_id == "E221"
    assert news.best.activated == ("نقل خبر",)


async def test_a_relation_works_from_either_end_and_on_the_arabic_label(db_session):
    as_object = await resolve_one(
        db_session,
        SceneLabel("cell phone", arabic="هاتف"),
        [SceneRelation(subject="شخص", predicate="مكالمة", object="هاتف")],
    )
    other_label = await resolve_one(
        db_session,
        "مطر",
        [SceneRelation(subject="كتاب", predicate="سقي", object="طفل")],
    )

    assert as_object.best.activated == ("مكالمة",)
    # A relation between two other things says nothing about this one.
    assert other_label.best.activated == ()


async def test_a_bonus_is_capped_and_a_score_never_passes_one(db_session, monkeypatch):
    from src.services import ontology_resolver

    monkeypatch.setattr(ontology_resolver, "CONTEXT_STEP", 0.2)
    relations = [SceneRelation("مطر", "سقي شرب هطول دعاء", "ماء")]

    resolution = await resolve_one(db_session, "مطر", relations)

    rain = resolution.best
    assert (rain.entity_id, rain.score) == ("E006", 1.0)
    assert len(rain.activated) == 4
    assert all(c.score <= 1.0 for c in resolution.candidates)
    # «ماء» (0.83) has two of those actions: two steps of 0.2, held to the cap of 0.1.
    water = next(c for c in resolution.candidates if c.entity_id == "E021")
    assert water.score == pytest.approx(0.93)


# ─── Several labels, strings and the embedding hook ───


async def test_a_scene_is_resolved_label_by_label_in_order(db_session):
    resolutions = await OntologyResolver(db_session).resolve(["person", "cell phone", "xyzzy"])

    assert [r.label.text for r in resolutions] == ["person", "cell phone", "xyzzy"]
    assert [r.best.entity_id for r in resolutions] == ["E161", "E221", "E1000"]
    assert await OntologyResolver(db_session).resolve([]) == []


async def test_a_person_label_resolves_to_the_generic_person_whose_constraint_blocks_inference(
    db_session,
):
    resolution = await resolve_one(db_session, "man")

    assert resolution.best.entity_id == "E161"
    assert resolution.best.special_constraint == "لا تُستنتج هوية الشخص أو علاقته"


class FakeEmbedder:
    def __init__(self, matches):
        self.matches = matches
        self.asked: list[tuple[str, int]] = []

    async def nearest(self, text, limit):
        self.asked.append((text, limit))
        return self.matches


async def test_the_embedding_hook_is_asked_only_when_the_text_layers_did_not_resolve(db_session):
    embedder = FakeEmbedder([EmbeddingMatch("E161", 0.9)])

    resolved = await resolve_one(db_session, "هاتف", embedder=embedder)
    unresolved = await resolve_one(db_session, "مخلوق غامض", embedder=embedder)

    assert resolved.best.entity_id == "E221"
    assert embedder.asked == [("مخلوق غامض", MAX_CANDIDATES)]
    suggestion = next(c for c in unresolved.candidates if c.entity_id == "E161")
    assert (suggestion.reason, suggestion.score) == (Reason.EMBEDDING, pytest.approx(0.54))


async def test_an_embedding_match_alone_never_resolves_a_label(db_session):
    embedder = FakeEmbedder([EmbeddingMatch("E161", 1.0), EmbeddingMatch("E9999", 1.0)])

    resolution = await resolve_one(db_session, "مخلوق غامض", embedder=embedder)

    assert RESOLVED_MIN_SCORE > 0.6
    assert resolution.resolved is False
    assert resolution.best.is_catch_all
    # An id the ontology does not have is ignored.
    assert ids(resolution) == ["E1000", "E161"]


async def test_the_embedding_hook_is_not_asked_about_a_label_with_nothing_to_embed(db_session):
    embedder = FakeEmbedder([EmbeddingMatch("E161", 1.0)])

    resolution = await resolve_one(db_session, "xyzzy", embedder=embedder)

    assert embedder.asked == []
    assert resolution.resolved is False


async def test_the_hints_can_be_replaced(db_session):
    resolution = await resolve_one(db_session, "zeppelin", hints={"zeppelin": ("جمل",)})

    assert resolution.best.entity_id == "E065"
