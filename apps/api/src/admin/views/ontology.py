"""The world ontology in the admin area: the candidates an editor reviews, and the entities."""

from __future__ import annotations

from typing import Any

from sqladmin import action
from sqladmin.filters import StaticValuesFilter
from sqlalchemy import update
from starlette.requests import Request
from starlette.responses import Response

from src import clock
from src.admin.base import (
    AdminView,
    ReadOnlyView,
    back_to_list,
    current_admin,
    labelled,
    selected_pks,
)
from src.models.ontology import (
    CandidateKind,
    CandidateStatus,
    OntologyCandidate,
    OntologyEntity,
)

CATEGORY = "Ontology"
CATEGORY_ICON = "fa-solid fa-sitemap"
NOTHING_SELECTED = "Select at least one candidate first."


class OntologyCandidateAdmin(AdminView, model=OntologyCandidate):
    """
    Terms a model proposed that the ontology does not hold, for an editor to decide.

    Accepting or rejecting records the decision, the time and the admin; an accepted
    term is merged into the next version of the workbook by hand, never into this table.
    The only field an editor types is the note.
    """

    name = "Ontology candidate"
    name_plural = "Ontology candidates"
    icon = "fa-solid fa-lightbulb"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        OntologyCandidate.id,
        OntologyCandidate.term,
        OntologyCandidate.kind,
        OntologyCandidate.count,
        OntologyCandidate.status,
        OntologyCandidate.sources,
        OntologyCandidate.last_seen_at,
        OntologyCandidate.reviewed_at,
        OntologyCandidate.reviewed_by,
    ]
    column_details_list = [
        OntologyCandidate.id,
        OntologyCandidate.term,
        OntologyCandidate.term_norm,
        OntologyCandidate.kind,
        OntologyCandidate.count,
        OntologyCandidate.sources,
        OntologyCandidate.examples,
        OntologyCandidate.status,
        OntologyCandidate.entity_id,
        OntologyCandidate.first_seen_at,
        OntologyCandidate.last_seen_at,
        OntologyCandidate.reviewed_at,
        OntologyCandidate.reviewed_by,
        OntologyCandidate.review_note,
    ]
    column_labels = labelled(column_details_list)
    column_searchable_list = [OntologyCandidate.term]
    column_sortable_list = [
        OntologyCandidate.count,
        OntologyCandidate.term,
        OntologyCandidate.last_seen_at,
        OntologyCandidate.reviewed_at,
    ]
    # The most often proposed first: they are the ones worth an editor's time.
    column_default_sort = [(OntologyCandidate.count, True)]
    column_filters = [
        StaticValuesFilter(
            OntologyCandidate.status,
            [(item.value, item.value) for item in CandidateStatus],
            "Status",
        ),
        StaticValuesFilter(
            OntologyCandidate.kind, [(item.value, item.value) for item in CandidateKind], "Kind"
        ),
    ]
    form_columns = [OntologyCandidate.review_note]
    can_create = False
    can_delete = False

    async def _review(self, request: Request, status: CandidateStatus) -> Response:
        ids = [int(pk) for pk in selected_pks(request) if pk.isdecimal()]
        if not ids:
            return back_to_list(request, self.identity, NOTHING_SELECTED)
        async with self.session_maker() as db:
            await db.execute(
                update(OntologyCandidate)
                .where(OntologyCandidate.id.in_(ids))
                .values(
                    status=status.value,
                    reviewed_at=clock.utcnow(),
                    reviewed_by=current_admin(request),
                )
            )
            await db.commit()
        return back_to_list(request, self.identity)

    @action(
        name="accept",
        label="Accept",
        confirmation_message="Accept the selected candidates? They go into the next version of the ontology.",
    )
    async def accept(self, request: Request) -> Response:
        return await self._review(request, CandidateStatus.ACCEPTED)

    @action(
        name="reject",
        label="Reject",
        confirmation_message="Reject the selected candidates?",
    )
    async def reject(self, request: Request) -> Response:
        return await self._review(request, CandidateStatus.REJECTED)

    async def on_model_change(
        self, data: dict[str, Any], model: Any, is_created: bool, request: Request
    ) -> None:
        """Editing the note counts as a review: the editor and the time are recorded with it."""
        model.reviewed_by = current_admin(request)
        model.reviewed_at = clock.utcnow()
        await super().on_model_change(data, model, is_created, request)


class OntologyEntityAdmin(ReadOnlyView, model=OntologyEntity):
    """The ontology as imported from the workbook; it is changed only by importing a new one."""

    name = "Ontology entity"
    name_plural = "Ontology entities"
    icon = "fa-solid fa-cubes"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        OntologyEntity.id,
        OntologyEntity.label_ar,
        OntologyEntity.domain,
        OntologyEntity.is_catch_all,
        OntologyEntity.special_constraint,
    ]
    column_details_list = [
        OntologyEntity.id,
        OntologyEntity.label_ar,
        OntologyEntity.domain,
        OntologyEntity.is_catch_all,
        OntologyEntity.special_constraint,
        OntologyEntity.related_objects,
        OntologyEntity.actions_and_uses,
        OntologyEntity.contextual_concepts,
        OntologyEntity.source_sha256,
        OntologyEntity.imported_at,
    ]
    column_labels = labelled(column_details_list)
    column_searchable_list = [OntologyEntity.label_ar, OntologyEntity.domain]
    column_sortable_list = [OntologyEntity.id, OntologyEntity.label_ar, OntologyEntity.domain]
    column_default_sort = [(OntologyEntity.id, False)]
