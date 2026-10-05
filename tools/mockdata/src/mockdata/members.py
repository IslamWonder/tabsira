"""Mock members: Arabic names, Latin handles, reserved e-mail domain. No private profile field."""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta

from faker import Faker

from mockdata.output import Member, stamp
from mockdata.places import COUNTRIES, City, country_quotas, pick_city

EMAIL_DOMAIN = "mock.tabsira.invalid"
SIGNUP_WINDOW_DAYS = 183  # about six months
HANDLE_MIN, HANDLE_MAX = 3, 30
_ARABIC_NAME = re.compile(r"^[ء-يٱ-ۓ\s]+$")
_HANDLE_JUNK = re.compile(r"[^a-z0-9_]")
FALLBACK_LOCALES = ("ar_PS", "ar_SA")
# Faker's name lists include a few names of notorious people; never use them for a mock member.
BLOCKED_NAME_PARTS = ("لادن", "هتلر")


class NameFactory:
    """Arabic display names and Latin handles from seeded Faker instances."""

    def __init__(self, seed: str) -> None:
        self._arabic: dict[str, Faker] = {}
        self._seed = seed
        self._latin = Faker("en_US")
        self._latin.seed_instance(seed + ":latin")

    def _faker(self, locale: str) -> Faker:
        if locale not in self._arabic:
            faker = Faker(locale)
            faker.seed_instance(f"{self._seed}:{locale}")
            self._arabic[locale] = faker
        return self._arabic[locale]

    def display_name(self, country: str) -> str:
        """A first and a last name; a locale that falls back to Latin script is skipped."""
        for locale in (*COUNTRIES[country][1], *FALLBACK_LOCALES):
            faker = self._faker(locale)
            for _ in range(5):
                name = f"{faker.first_name()} {faker.last_name()}"
                if _ARABIC_NAME.match(name) and not any(b in name for b in BLOCKED_NAME_PARTS):
                    return name
        # Unreachable while the fallback locales speak Arabic; kept as a visible failure.
        message = f"no Arabic name for {country}"
        raise RuntimeError(message)

    def handle(self, taken: set[str]) -> str:
        base = _HANDLE_JUNK.sub("", self._latin.user_name().lower().replace(".", "_"))
        base = base[: HANDLE_MAX - 4].ljust(HANDLE_MIN, "x")
        handle, n = base, 1
        while handle in taken:
            n += 1
            handle = f"{base}{n}"
        taken.add(handle)
        return handle


def make_members(
    seed: int,
    total: int,
    now: datetime,
    cities_by_country: dict[str, list[City]],
) -> list[Member]:
    """`total` members, countries by square-root quota, cities by population, sign-ups spread."""
    rng = random.Random(f"{seed}:members")
    names = NameFactory(f"{seed}:names")
    taken: set[str] = set()
    members: list[Member] = []
    for country, quota in country_quotas(total).items():
        for _ in range(quota):
            city = pick_city(rng, cities_by_country[country])
            handle = names.handle(taken)
            joined = now - timedelta(seconds=rng.randrange(SIGNUP_WINDOW_DAYS * 86400))
            members.append(
                Member(
                    ref="",
                    handle=handle,
                    display_name=names.display_name(country),
                    email=f"{handle}@{EMAIL_DOMAIN}",
                    country=country,
                    city_geoname_id=city.geoname_id,
                    joined_at=stamp(joined),
                )
            )
    rng.shuffle(members)
    return [m.model_copy(update={"ref": f"m{i:04d}"}) for i, m in enumerate(members, start=1)]
