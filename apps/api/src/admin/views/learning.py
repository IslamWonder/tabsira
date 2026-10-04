"""The learning path in the admin area: its versions, domains and units, read-only."""

from __future__ import annotations

from sqladmin import action
from sqladmin.filters import BooleanFilter
from sqlalchemy import update
from starlette.requests import Request
from starlette.responses import Response

from src.admin.base import ReadOnlyView, back_to_list, labelled, selected_pks
from src.models.learning import LearningDomain, LearningPathVersion, LearningUnit

CATEGORY = "Learning path"
CATEGORY_ICON = "fa-solid fa-route"
ONE_VERSION = "Select exactly one version to activate."


class LearningPathVersionAdmin(ReadOnlyView, model=LearningPathVersion):
    """
    The releases of the learning path.

    Their content is imported, never edited here; the one thing an admin does is choose
    which version learners follow.
    """

    name = "Learning path version"
    name_plural = "Learning path versions"
    icon = "fa-solid fa-code-branch"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        LearningPathVersion.path_version,
        LearningPathVersion.title,
        LearningPathVersion.version,
        LearningPathVersion.released_on,
        LearningPathVersion.domain_count,
        LearningPathVersion.unit_count,
        LearningPathVersion.is_active,
        LearningPathVersion.imported_at,
    ]
    column_details_list = [
        *column_list,
        LearningPathVersion.description,
        LearningPathVersion.source_file,
        LearningPathVersion.source_sha256,
    ]
    column_labels = labelled(column_details_list)
    column_sortable_list = [LearningPathVersion.released_on, LearningPathVersion.imported_at]
    column_default_sort = [(LearningPathVersion.imported_at, True)]
    column_filters = [BooleanFilter(LearningPathVersion.is_active, "Active")]

    @action(
        name="activate",
        label="Activate version",
        confirmation_message="Make this the version learners follow? The active one is switched off.",
    )
    async def activate(self, request: Request) -> Response:
        """Make one version the active one; at most one is, which the database enforces."""
        chosen = selected_pks(request)
        if len(chosen) != 1:
            return back_to_list(request, self.identity, ONE_VERSION)
        async with self.session_maker() as db:
            exists = await db.get(LearningPathVersion, chosen[0])
            if exists is None:
                return back_to_list(request, self.identity, ONE_VERSION)
            # Two statements, in this order: the unique index allows one active row at a time.
            await db.execute(
                update(LearningPathVersion)
                .where(LearningPathVersion.is_active.is_(True))
                .values(is_active=False)
            )
            await db.execute(
                update(LearningPathVersion)
                .where(LearningPathVersion.path_version == chosen[0])
                .values(is_active=True)
            )
            await db.commit()
        return back_to_list(request, self.identity)


class LearningDomainAdmin(ReadOnlyView, model=LearningDomain):
    name = "Learning domain"
    name_plural = "Learning domains"
    icon = "fa-solid fa-layer-group"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        LearningDomain.path_version,
        LearningDomain.id,
        LearningDomain.position,
        LearningDomain.title,
        LearningDomain.function,
    ]
    column_details_list = [*column_list, LearningDomain.goal, LearningDomain.concepts]
    column_labels = labelled(column_details_list)
    column_searchable_list = [LearningDomain.title]
    column_sortable_list = [LearningDomain.path_version, LearningDomain.position]
    column_default_sort = [(LearningDomain.path_version, True), (LearningDomain.position, False)]


class LearningUnitAdmin(ReadOnlyView, model=LearningUnit):
    """A unit of the path. Evidence references are pointers, never the text of a verse or a hadith."""

    name = "Learning unit"
    name_plural = "Learning units"
    icon = "fa-solid fa-book-open"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        LearningUnit.path_version,
        LearningUnit.id,
        LearningUnit.domain_id,
        LearningUnit.position,
        LearningUnit.title,
    ]
    column_details_list = [
        *column_list,
        LearningUnit.objectives,
        LearningUnit.prerequisites,
        LearningUnit.depths,
        LearningUnit.concepts,
        LearningUnit.evidence_refs,
        LearningUnit.source_anchors,
    ]
    column_labels = labelled(column_details_list)
    column_searchable_list = [LearningUnit.title, LearningUnit.id]
    column_sortable_list = [
        LearningUnit.path_version,
        LearningUnit.domain_id,
        LearningUnit.position,
    ]
    column_default_sort = [
        (LearningUnit.path_version, True),
        (LearningUnit.domain_id, False),
        (LearningUnit.position, False),
    ]
