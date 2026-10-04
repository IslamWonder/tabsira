"""
The public identity, public profiles, follows and blocks.

A profile is public and needs no session; a follow or a block needs one. People are named by
their handle only: an account's own id never appears in a path or a response, so knowing
someone's id grants nothing and an id cannot be used to find a handle.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from src.deps import (
    CurrentUser,
    DbDep,
    OptionalUser,
    VerifiedUser,
    limited,
    require_social,
)
from src.errors import AppError, ErrorCode
from src.schemas.social import MemberOut, MemberProfileOut, PublicIdentityIn, PublicIdentityOut
from src.services import block_service, member_service, public_identity
from src.services.social_limits import WriteKind

router = APIRouter(tags=["members"], dependencies=[Depends(require_social)])


@router.get("/me/public-identity", summary="The caller's handle and public name")
async def get_public_identity(user: CurrentUser) -> PublicIdentityOut:
    """Return the identity the caller appears under, or nulls until they choose one."""
    return PublicIdentityOut(handle=user.handle, public_name=user.public_name)


@router.put(
    "/me/public-identity",
    summary="Choose or change the handle and public name",
    dependencies=[limited(WriteKind.IDENTITY)],
)
async def put_public_identity(
    body: PublicIdentityIn, user: VerifiedUser, db: DbDep
) -> PublicIdentityOut:
    """
    Set the handle (`/u/<handle>`) and the name every public page shows for the caller.

    Needs a verified e-mail address. The handle is unique whatever its case: 409
    `HANDLE_TAKEN` when somebody else holds it. The account's own name is never used.
    """
    await public_identity.set_public_identity(
        db, user, handle=body.handle, public_name=body.public_name
    )
    await db.commit()
    return PublicIdentityOut(handle=user.handle, public_name=user.public_name)


@router.get("/u/{handle}", summary="A public profile")
async def get_profile(handle: str, viewer: OptionalUser, db: DbDep) -> MemberProfileOut:
    """
    Return a member's public profile: handle, public name, month joined and three counts.

    404 for a handle nobody holds, and for one that a block stands in front of, in either
    direction. Nothing from the member's private profile, and no e-mail address, ever.
    """
    member = await member_service.visible_member(db, handle, viewer)
    return await member_service.profile_of(db, member, viewer)


@router.put(
    "/u/{handle}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Follow a member",
    dependencies=[limited(WriteKind.REACTION)],
)
async def follow_member(handle: str, user: VerifiedUser, db: DbDep) -> Response:
    """Follow a member; following again changes nothing. 400 for oneself."""
    target = await member_service.visible_member(db, handle, user)
    await member_service.follow(db, user, target)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/u/{handle}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop following a member",
    dependencies=[limited(WriteKind.REACTION)],
)
async def unfollow_member(handle: str, user: CurrentUser, db: DbDep) -> Response:
    """Stop following a member; safe to repeat."""
    target = await member_service.visible_member(db, handle, user)
    await member_service.unfollow(db, user, target)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/blocks", summary="The members the caller has blocked")
async def list_blocks(user: CurrentUser, db: DbDep) -> list[MemberOut]:
    """List the members the caller blocked, newest first, by handle and public name only."""
    blocked = await block_service.blocked_accounts(db, user)
    return [
        MemberOut(handle=member.handle, public_name=member.public_name)
        for member in blocked
        if member.handle is not None and member.public_name is not None
    ]


@router.put(
    "/blocks/{handle}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Block a member",
    dependencies=[limited(WriteKind.BLOCK)],
)
async def block_member(handle: str, user: CurrentUser, db: DbDep) -> Response:
    """
    Block a member.

    Each of the two stops seeing the other everywhere, and the follows between them, in
    both directions, end. Blocking again changes nothing. 400 for oneself.
    """
    target = await public_identity.find_member(db, handle)
    if target is None:
        raise member_service.not_found()
    if target.id == user.id:
        raise AppError(ErrorCode.BAD_REQUEST, "You cannot block yourself.", status_code=400)
    await block_service.block(db, user, target)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/blocks/{handle}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Lift a block",
    dependencies=[limited(WriteKind.BLOCK)],
)
async def unblock_member(handle: str, user: CurrentUser, db: DbDep) -> Response:
    """Lift the caller's own block; safe to repeat."""
    target = await public_identity.find_member(db, handle)
    if target is None:
        raise member_service.not_found()
    await block_service.unblock(db, user, target)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
