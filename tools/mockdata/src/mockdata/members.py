"""
Mock members with a complete profile, as the people who signed up and filled the form.

Reviewed Arabic names that match the declared gender, handles that read like them, the reserved
mock e-mail domain, and every private profile field (private, as for every member).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from mockdata.names import FAMILY, FAMILY_BY_COUNTRY, FEMALE, MALE
from mockdata.output import Member, stamp
from mockdata.places import City, country_quotas, pick_city

EMAIL_DOMAIN = "mock.tabsira.me"
SIGNUP_WINDOW_DAYS = 183  # about six months
HANDLE_MIN, HANDLE_MAX = 3, 30
# Shares of the declared genders; the rest answered «أفضّل عدم الإجابة».
WOMAN_SHARE = 0.47
UNKNOWN_SHARE = 0.06
GOALS = (
    "discover_islam",
    "reflection",
    "learn_quran_sunnah",
    "live_values",
    "research",
    "teaching",
    "curiosity",
)
# (value, weight). No child: a mock member is never under 13, and none declares 13 to 17.
AGE_RANGES = (("18_24", 30), ("25_39", 38), ("40_59", 20), ("60_plus", 4), ("unknown", 8))
KNOWLEDGE = (("new", 25), ("general", 40), ("advanced", 20), ("specialist", 5), ("unknown", 10))
BACKGROUNDS = (("muslim", 88), ("unknown", 8), ("non_muslim", 4))
THEMES = (("system", 40), ("light", 30), ("dark", 30))
MOTIONS = (("system", 80), ("on", 10), ("off", 10))
FULL_NAME_SHARE = 0.35
SOUND_SHARE = 0.2


def weighted(rng: random.Random, options: tuple[tuple[str, int], ...]) -> str:
    return rng.choices([v for v, _ in options], weights=[w for _, w in options])[0]


class NameFactory:
    """Arabic names by gender and handles built from their Latin spelling, from seeded draws."""

    def __init__(self, seed: str) -> None:
        self._rng = random.Random(f"{seed}:names")
        self._gender = random.Random(f"{seed}:gender")

    def gender(self) -> str:
        """The declared gender: man, woman, or unknown (a name of either list then)."""
        draw = self._gender.random()
        if draw < UNKNOWN_SHARE:
            return "unknown"
        return "woman" if draw < UNKNOWN_SHARE + WOMAN_SHARE else "man"

    def person(self, gender: str, country: str) -> tuple[str, str, str]:
        """
        (Arabic full name, Latin first name, Latin family name).

        The first name fits the gender and the family name the country.
        """
        pool = {"man": MALE, "woman": FEMALE}.get(gender) or self._rng.choice((MALE, FEMALE))
        first_ar, first_latin = self._rng.choice(pool)
        family_ar, family_latin = self._rng.choice(FAMILY_BY_COUNTRY.get(country, FAMILY))
        return f"{first_ar} {family_ar}", first_latin, family_latin

    def handle(self, first: str, family: str, taken: set[str]) -> str:
        """A handle that reads like the name, unique whatever the case, 3 to 30 characters."""
        style = self._rng.random()
        if style < 0.4:
            base = f"{first}_{family}"
        elif style < 0.7:
            base = f"{first}{self._rng.randrange(10, 100)}"
        else:
            base = f"{first[0]}{family}{self._rng.randrange(1, 100)}"
        base = base[: HANDLE_MAX - 4].ljust(HANDLE_MIN, "x")
        handle, n = base, 1
        while handle in taken:
            n += 1
            handle = f"{base}{n}"
        taken.add(handle)
        return handle


def profile_of(rng: random.Random, gender: str) -> dict[str, object]:
    """What the person declared in the profile form: private, varied, never under 13."""
    return {
        "gender": gender,
        "age_range": weighted(rng, AGE_RANGES),
        "goals": sorted(rng.sample(GOALS, rng.randint(1, 3))),
        "knowledge_level": weighted(rng, KNOWLEDGE),
        "religious_background": weighted(rng, BACKGROUNDS),
        "theme": weighted(rng, THEMES),
        "reduced_motion": weighted(rng, MOTIONS),
        "sound": rng.random() < SOUND_SHARE,
        "public_full_name": rng.random() < FULL_NAME_SHARE,
    }


def make_members(
    seed: int,
    total: int,
    now: datetime,
    cities_by_country: dict[str, list[City]],
) -> list[Member]:
    """`total` members, countries by square-root quota, cities by population, sign-ups spread."""
    rng = random.Random(f"{seed}:members")
    profiles = random.Random(f"{seed}:profiles")
    names = NameFactory(f"{seed}:names")
    taken: set[str] = set()
    members: list[Member] = []
    for country, quota in country_quotas(total).items():
        for _ in range(quota):
            city = pick_city(rng, cities_by_country[country])
            joined = now - timedelta(seconds=rng.randrange(SIGNUP_WINDOW_DAYS * 86400))
            gender = names.gender()
            full_name, first, family = names.person(gender, country)
            handle = names.handle(first, family, taken)
            members.append(
                Member(
                    ref="",
                    handle=handle,
                    display_name=full_name,
                    email=f"{handle}@{EMAIL_DOMAIN}",
                    country=country,
                    city_geoname_id=city.geoname_id,
                    joined_at=stamp(joined),
                    **profile_of(profiles, gender),
                )
            )
    rng.shuffle(members)
    return [m.model_copy(update={"ref": f"m{i:04d}"}) for i, m in enumerate(members, start=1)]
