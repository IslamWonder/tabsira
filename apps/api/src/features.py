"""
The feature switches: one enum, two lists in the environment, one rule (decision 63).

`DISABLED_FEATURES` names what is switched off, `ENABLED_FEATURES` what is switched on although
it is off by default. The web app applies the same rule (apps/web/src/config/server-env.ts) to
the same two keys, so a feature is on or off for both at once.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum


class FeatureFlag(StrEnum):
    """A switchable feature; the value is the name used in the two lists."""

    # The core journey's optional parts.
    CHAT = "chat"  # the three-answer chat of an insight
    WORLD = "world"  # the personal world, completion, public insight pages
    TREASURE = "treasure"  # the treasure found on completion

    # What the evidence cards show beside the stored text.
    HADITH_RULING = "hadith_ruling"  # the first grader's ruling of the hadith's dataset
    QURAN_SOURCE_LINK = "quran_source_link"  # «افتح في قرآنبيديا» on the verse card; off by default

    # The network «تبصرة تواصل».
    SOCIAL = "social"  # posts, feeds, follows, reactions, public profiles
    SOCIAL_COMMENTS = "social_comments"  # comments under posts; off until the owners enable them

    # The world atlas and the camera discovery.
    ATLAS = "atlas"  # the map and its entries
    ATLAS_SPONSORSHIP = "atlas_sponsorship"  # «كفالة بصيرة» (decision 60)
    CAMERA_DISCOVERY = "camera_discovery"  # nearby entries in the camera view
    CAMERA_ANCHOR = "camera_anchor"  # level C, anchoring; off until proven on devices

    # Storage and verification.
    PHOTO_STORAGE = "photo_storage"  # keeping consented photos
    CANONICAL_VERIFY = "canonical_verify"  # the daily check of the Quran text

    # Operations.
    ADMIN = "admin"  # the admin area (decision 14)
    DEV_INSPECTOR = "dev_inspector"  # the scan inspector of v2 §23, in the admin area


# On only when named in ENABLED_FEATURES.
OFF_BY_DEFAULT: frozenset[FeatureFlag] = frozenset(
    {FeatureFlag.SOCIAL_COMMENTS, FeatureFlag.CAMERA_ANCHOR, FeatureFlag.QURAN_SOURCE_LINK}
)

# child -> parent: a child counts as off whenever its parent is off.
PARENT: Mapping[FeatureFlag, FeatureFlag] = {
    FeatureFlag.SOCIAL_COMMENTS: FeatureFlag.SOCIAL,
    FeatureFlag.ATLAS_SPONSORSHIP: FeatureFlag.ATLAS,
    FeatureFlag.CAMERA_ANCHOR: FeatureFlag.CAMERA_DISCOVERY,
    FeatureFlag.DEV_INSPECTOR: FeatureFlag.ADMIN,
}


def parse_flags(raw: str, key: str) -> frozenset[FeatureFlag]:
    """Return the flags a comma-separated list names; refuse a name that is not a feature."""
    names = [name.strip() for name in raw.split(",") if name.strip()]
    valid = {flag.value for flag in FeatureFlag}
    unknown = [name for name in names if name not in valid]
    if unknown:
        message = (
            f"{key} names no such feature: {', '.join(unknown)}. "
            f"Valid names: {', '.join(sorted(valid))}"
        )
        raise ValueError(message)
    return frozenset(FeatureFlag(name) for name in names)


def active_flags(
    disabled: Iterable[FeatureFlag], enabled: Iterable[FeatureFlag]
) -> frozenset[FeatureFlag]:
    """Return the features that are on, by the rule of decision 63."""
    off, on = frozenset(disabled), frozenset(enabled)

    def own(flag: FeatureFlag) -> bool:
        if flag in on:
            return True
        return flag not in OFF_BY_DEFAULT and flag not in off

    def is_on(flag: FeatureFlag) -> bool:
        parent = PARENT.get(flag)
        return own(flag) and (parent is None or is_on(parent))

    return frozenset(flag for flag in FeatureFlag if is_on(flag))


_TRUE_WORDS = frozenset({"1", "true", "yes", "on"})


def legacy_advice(key: str, value: str) -> str:
    """Say what replaces a `FEATURE_<NAME>` key of the earlier scheme; those keys are refused."""
    name = key.lower().removeprefix("feature_")
    if name == "public_pages":
        name = FeatureFlag.SOCIAL.value  # decision 54
    try:
        flag = FeatureFlag(name)
    except ValueError:
        return f"{key.upper()} is no longer read and names no feature: remove it"
    turned_on = value.strip().lower() in _TRUE_WORDS
    if turned_on and flag in OFF_BY_DEFAULT:
        return f"{key.upper()}={value}: put {flag.value} in ENABLED_FEATURES and remove the key"
    if turned_on:
        return f"{key.upper()}={value}: remove it, {flag.value} is on by default"
    if flag in OFF_BY_DEFAULT:
        return f"{key.upper()}={value}: remove it, {flag.value} is off by default"
    return f"{key.upper()}={value}: put {flag.value} in DISABLED_FEATURES and remove the key"
