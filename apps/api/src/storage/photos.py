"""
What may be kept, and when: the rules of master prompt v2 section 19, in code.

`Storage` keeps whatever it is given. This module is the only way a photo gets there, and it
refuses before anything is written when any of these holds (`PhotoRefusal`):

- the feature is switched off (the `photo_storage` feature);
- the person is a guest: nothing is kept for someone with no account;
- the person said they are under 13;
- the scene is sensitive: it is never kept, never shown back, never published;
- the account has not agreed to keep photos (`photo_storage_consent`).

Every one of those facts is a required keyword argument of `PhotoFacts`, with no default, so
a caller cannot forget to say it, and a new caller that does not know the answer has to
write down that it does not. `owner_id=None` is the only way to say "guest".

Publishing copies the private object to a new `public/` key, and withdrawing deletes that copy.
It repeats the checks, because the facts may have changed since the photo was kept: a sensitive
scene is never published, and neither is a photo of someone who has since said they are under
13 or who has withdrawn their consent.

Whether the caller may touch a given key at all, that is, that the key belongs to the person
asking, is the route's check and comes first: a key is a random string, not a permission.
`src/services/photo_service.py` is the one caller: it keeps the photo at «تمّ», makes and
removes the public copy with the publications, and deletes everything with the account.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from src.config import Settings
from src.features import FeatureFlag
from src.models.profile import AgeRange
from src.services.image_service import ProcessedPhoto
from src.storage import build_storage
from src.storage.base import (
    InvalidKeyError,
    Storage,
    StorageError,
    check_key,
    is_public_key,
    new_private_key,
    new_public_key,
    owner_prefix,
)


class PhotoRefusal(StrEnum):
    """Why a photo may not be kept or published."""

    FEATURE_OFF = "feature_off"
    GUEST = "guest"
    UNDER_13 = "under_13"
    SENSITIVE_SCENE = "sensitive_scene"
    NO_CONSENT = "no_consent"


class PhotoNotAllowedError(StorageError):
    """A photo was not kept or published because of its `reason`."""

    def __init__(self, reason: PhotoRefusal) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True, kw_only=True)
class PhotoFacts:
    """
    What a caller must state about a photo before it may be kept or published.

    `owner_id` is the signed-in account, or None for a guest. `age_range` is what the account
    said about itself (`AgeRange.UNKNOWN` when it said nothing; age is never guessed from a
    photo). `sensitive_scene` is the pipeline's own verdict on the scene. `photo_storage_consent`
    is the account's switch for keeping photos.
    """

    owner_id: uuid.UUID | None
    age_range: AgeRange
    sensitive_scene: bool
    photo_storage_consent: bool

    def __post_init__(self) -> None:
        """Refuse a fact of the wrong kind: `"under_13"` as a plain string must still count."""
        try:
            age_range = AgeRange(self.age_range)
        except ValueError as error:
            message = f"age_range is not a known age range: {self.age_range!r}"
            raise ValueError(message) from error
        object.__setattr__(self, "age_range", age_range)
        for name in ("sensitive_scene", "photo_storage_consent"):
            if not isinstance(getattr(self, name), bool):
                message = f"{name} must be a bool"
                raise TypeError(message)

    def refusal(self, settings: Settings) -> PhotoRefusal | None:
        """Return the first reason the photo may not be kept, or None when it may."""
        if not settings.is_enabled(FeatureFlag.PHOTO_STORAGE):
            return PhotoRefusal.FEATURE_OFF
        if self.owner_id is None:
            return PhotoRefusal.GUEST
        if self.age_range is AgeRange.UNDER_13:
            return PhotoRefusal.UNDER_13
        if self.sensitive_scene:
            return PhotoRefusal.SENSITIVE_SCENE
        if not self.photo_storage_consent:
            return PhotoRefusal.NO_CONSENT
        return None


@dataclass(frozen=True)
class StoredPhoto:
    """An owner's private copy: its key, and the size of the image kept."""

    key: str
    width: int
    height: int


@dataclass(frozen=True)
class PublishedPhoto:
    """A published copy: its public key and the address anyone can read it at."""

    key: str
    url: str


class PhotoStore:
    """Keeps, publishes and removes photos, after the checks above."""

    def __init__(self, storage: Storage, settings: Settings) -> None:
        self.storage = storage
        self.settings = settings

    def _require(self, facts: PhotoFacts) -> None:
        reason = facts.refusal(self.settings)
        if reason is not None:
            raise PhotoNotAllowedError(reason)

    async def keep(self, facts: PhotoFacts, photo: ProcessedPhoto) -> StoredPhoto:
        """Store the clean image as the owner's private copy, or raise `PhotoNotAllowedError`."""
        self._require(facts)
        # Kept only for an account (`_require` refuses a guest): in that account's folder.
        key = new_private_key(facts.owner_id)
        await self.storage.put(key, photo.data, content_type=photo.content_type)
        return StoredPhoto(key=key, width=photo.width, height=photo.height)

    async def publish(self, facts: PhotoFacts, private_key: str) -> PublishedPhoto:
        """Copy a private photo to a new public key. The owner's own act, so the route asks."""
        self._require(facts)
        if is_public_key(private_key):
            message = "only a private copy can be published"
            raise InvalidKeyError(message)
        public_key = new_public_key()
        await self.storage.copy(private_key, public_key)
        return PublishedPhoto(key=public_key, url=self.storage.public_url(public_key))

    async def withdraw(self, public_key: str) -> None:
        """Delete a published copy. Always allowed: taking a photo down needs no permission."""
        if not is_public_key(public_key):
            message = "only a published copy can be withdrawn"
            raise InvalidKeyError(message)
        await self.storage.delete(public_key)

    async def remove_owner(self, owner_id: uuid.UUID) -> int:
        """Delete everything left in one account's private folder; return how many objects."""
        return await self.storage.delete_prefix(owner_prefix(owner_id))

    async def remove(self, private_key: str) -> None:
        """Delete an owner's private copy. The caller withdraws the public copy first."""
        if is_public_key(private_key):
            message = "use withdraw for a published copy"
            raise InvalidKeyError(message)
        await self.storage.delete(private_key)

    def private_url(self, private_key: str, *, ttl_seconds: int | None = None) -> str:
        """Return a short-lived signed link to a private photo, for its owner to see it."""
        if is_public_key(check_key(private_key)):
            message = "a published copy has a public address, not a signed one"
            raise InvalidKeyError(message)
        return self.storage.signed_url(private_key, ttl_seconds=ttl_seconds)


def build_photo_store(settings: Settings) -> PhotoStore:
    """Build the photo store for the storage the settings name."""
    return PhotoStore(build_storage(settings), settings)
