"""
The body of `GET /community/summary`: a few counts of what anyone can already see.

Every figure is an aggregate of public things (published public posts, published map entries
and their public reactions), never a list, a person or a place. A figure whose feature is
switched off is `null`, so a client never shows a count of something it cannot open.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CommunitySummary(BaseModel):
    """How large the community looks to a visitor."""

    members: int = Field(
        ge=0,
        description="Accounts with at least one published public post or published map entry.",
    )
    insights: int | None = Field(
        ge=0, description="Published public posts; null while the network is off."
    )
    reactions: int | None = Field(
        ge=0, description="Reactions on published public posts; null while the network is off."
    )
    atlas_entries: int | None = Field(
        ge=0, description="Entries shown on the atlas; null while the atlas is off."
    )
    countries: int | None = Field(
        ge=0, description="Distinct countries of the atlas entries; null while the atlas is off."
    )
    sponsorships_open: int | None = Field(
        ge=0,
        description="Atlas entries waiting for a sponsor («كفالة»); null while sponsoring is off.",
    )
