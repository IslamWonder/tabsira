"""
Request and response bodies of the social network.

What a public response may say about a person is exactly a handle and a public name, and
for a profile the month they joined and three counts. No schema here has a field for an
e-mail address, the account's own name, a private profile answer or a place; a test lists
every field of every schema, so adding one fails the build until it is justified.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.services import public_identity


class PublicIdentityIn(BaseModel):
    """The handle and public name an account chooses to appear under."""

    model_config = ConfigDict(extra="forbid")

    handle: Annotated[str, Field(min_length=1, max_length=64)]
    public_name: Annotated[str, Field(min_length=1, max_length=160)]

    @field_validator("handle")
    @classmethod
    def _handle(cls, value: str) -> str:
        handle = public_identity.clean_handle(value)
        problem = public_identity.handle_problem(handle)
        if problem is not None:
            raise ValueError(problem)
        return handle

    @field_validator("public_name")
    @classmethod
    def _public_name(cls, value: str) -> str:
        name = public_identity.clean_public_name(value)
        problem = public_identity.public_name_problem(name)
        if problem is not None:
            raise ValueError(problem)
        return name


class PublicIdentityOut(BaseModel):
    """The caller's own handle and public name; both null until they have chosen."""

    handle: str | None
    public_name: str | None


class MemberOut(BaseModel):
    """A person as the network shows them: the two things they chose, and nothing else."""

    model_config = ConfigDict(from_attributes=True)

    handle: str
    public_name: str


class ViewerRelationOut(BaseModel):
    """How the signed-in viewer stands to a profile."""

    follows: bool
    is_self: bool


class MemberProfileOut(MemberOut):
    """A public profile: who, since when, and three counts read from the rows they count."""

    joined_month: str = Field(description="`YYYY-MM`, in UTC")
    posts_count: int = Field(description="Published public posts")
    followers_count: int
    following_count: int
    viewer: ViewerRelationOut | None = Field(description="Null for a guest")
