"""
The readers' ratings of their insights, for the team to improve the answers.

Read-only: the rating is the owner's, so the admin only reads it and marks it reviewed.
A rating changed by its owner comes back as open. The list shows the reasons and the
note, never the photo; the insight id leads to the scan inspector where it is on.
"""

from __future__ import annotations

from sqladmin import action
from sqladmin.filters import BooleanFilter, StaticValuesFilter
from sqlalchemy import update
from starlette.requests import Request
from starlette.responses import Response

from src.admin.base import ReadOnlyView, back_to_list, labelled, selected_pks
from src.models.scan import FeedbackState, InsightFeedback

NOTHING_SELECTED = "Select at least one rating."


class InsightFeedbackAdmin(ReadOnlyView, model=InsightFeedback):
    """The ratings, newest first; the «not useful» ones are what to read."""

    name = "Insight rating"
    name_plural = "Insight ratings"
    icon = "fa-solid fa-thumbs-up"
    category = "Quality"
    category_icon = "fa-solid fa-star-half-stroke"

    column_list = [
        InsightFeedback.id,
        InsightFeedback.insight_id,
        InsightFeedback.helpful,
        InsightFeedback.reasons,
        InsightFeedback.note,
        InsightFeedback.state,
        InsightFeedback.updated_at,
    ]
    column_details_list = [*column_list, InsightFeedback.created_at]
    column_labels = labelled(column_details_list)
    column_sortable_list = [InsightFeedback.updated_at, InsightFeedback.helpful]
    column_default_sort = [(InsightFeedback.updated_at, True)]
    column_filters = [
        BooleanFilter(InsightFeedback.helpful, "Useful"),
        StaticValuesFilter(
            InsightFeedback.state, [(state.value, state.value) for state in FeedbackState], "State"
        ),
    ]

    @action(
        name="reviewed",
        label="Mark reviewed",
        confirmation_message="Mark the selected ratings as reviewed?",
    )
    async def mark_reviewed(self, request: Request) -> Response:
        """Close the ticked ratings; the owner changing one opens it again."""
        chosen = [int(pk) for pk in selected_pks(request) if pk.isdigit()]
        if not chosen:
            return back_to_list(request, self.identity, NOTHING_SELECTED)
        async with self.session_maker() as db:
            await db.execute(
                update(InsightFeedback)
                .where(InsightFeedback.id.in_(chosen))
                .values(state=FeedbackState.REVIEWED)
            )
            await db.commit()
        return back_to_list(request, self.identity)
