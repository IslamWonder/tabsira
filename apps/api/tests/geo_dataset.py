"""
A small world for the geo tests: a few countries, regions, cities and names.

One definition, two uses: `load_world` inserts it through the models, for the
service and route tests; `write_dump` writes the same places as GeoNames dump
files, with the noise a real dump has (lakes, other languages), for the tests
of the import scripts, which must end with the same database.

Ids are the real GeoNames ones where it matters little; the places called Zero
Point, Eastern Edge and Western Edge exist to test coordinates of zero and the
antimeridian.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import GeoAlternateName, GeoCountryInfo, GeoName

TUNIS = (36.8065, 10.1815)
MECCA = (21.4225, 39.8262)

TUNISIA = 2464461
SAUDI_ARABIA = 102358
FRANCE = 3017382
TUNIS_GOVERNORATE = 2464464
MECCA_REGION = 104514
RIYADH_REGION = 108412
TUNIS_CITY = 2464470
HAMMAM_LIF = 2470588
BAB_SOUIKA = 2473000
CARTHAGE_HISTORICAL = 2473001
SMALLTOWN = 2473002
SFAX = 2467454
OLD_TUNIS = 2999999
TUNIS_ELSEWHERE = 4000001
MECCA_CITY = 104515
MEDINA = 109223
RIYADH = 108410
PARIS = 2988507
ZERO_POINT = 5000000
EASTERN_EDGE = 5000001
WESTERN_EDGE = 5000002


def place(
    geoname_id: int,
    name: str,
    lat: float,
    lng: float,
    feature_class: str,
    feature_code: str,
    country: str | None,
    admin1: str | None,
    population: int | None,
    ar_name: str | None = None,
    *,
    active: bool = True,
) -> dict[str, Any]:
    return {
        "geoname_id": geoname_id,
        "name": name,
        "latitude": lat,
        "longitude": lng,
        "feature_class": feature_class,
        "feature_code": feature_code,
        "country_code": country,
        "admin1_code": admin1,
        "population": population,
        # What the import must derive from the Arabic names below.
        "ar_name": ar_name,
        "is_active": active,
    }


PLACES = [
    place(TUNISIA, "Republic of Tunisia", 34.0, 9.0, "A", "PCLI", "TN", "00", 11565204, "تونس"),
    place(
        SAUDI_ARABIA,
        "Kingdom of Saudi Arabia",
        25.0,
        45.0,
        "A",
        "PCLI",
        "SA",
        "00",
        25731776,
        "المملكة العربية السعودية",
    ),
    place(
        TUNIS_GOVERNORATE,
        "Gouvernorat de Tunis",
        36.8,
        10.2,
        "A",
        "ADM1",
        "TN",
        "36",
        1056247,
        "ولاية تونس",
    ),
    place(
        MECCA_REGION, "Mecca Region", 21.5, 40.5, "A", "ADM1", "SA", "14", 8557766, "مكة المكرّمة"
    ),
    place(
        RIYADH_REGION, "Riyadh Region", 24.6, 46.7, "A", "ADM1", "SA", "10", 8591748, "منطقة الرياض"
    ),
    place(TUNIS_CITY, "Tunis", 36.81897, 10.16579, "P", "PPLC", "TN", "36", 693210, "تونس"),
    place(HAMMAM_LIF, "Hammam-Lif", 36.72962, 10.3344, "P", "PPL", "TN", "36", 44207, "حمام الأنف"),
    place(BAB_SOUIKA, "Bab Souika", 36.8, 10.17, "P", "PPLX", "TN", "36", 0),
    place(CARTHAGE_HISTORICAL, "Carthage", 36.853, 10.323, "P", "PPLH", "TN", "36", 0),
    place(SMALLTOWN, "Smalltown", 36.5, 10.0, "P", "PPL", "TN", "36", 5000),
    place(SFAX, "Sfax", 34.74056, 10.76028, "P", "PPLA", "TN", "32", 280566, "صفاقس"),
    place(OLD_TUNIS, "Old Tunis", 36.81, 10.17, "P", "PPL", "TN", "36", 900000000, "تونس القديمة"),
    place(TUNIS_ELSEWHERE, "Tunis", 30.0, -91.0, "P", "PPL", "US", "LA", 300),
    place(
        MECCA_CITY, "Makkah", 21.42664, 39.82563, "P", "PPLA", "SA", "14", 1578722, "مكة المكرمة"
    ),
    place(
        MEDINA,
        "Al Madinah",
        24.46861,
        39.61417,
        "P",
        "PPLA",
        "SA",
        "05",
        1300000,
        "المدينة المنورة",
    ),
    place(RIYADH, "Riyadh", 24.68773, 46.72185, "P", "PPLC", "SA", "10", 5188286, "الرياض"),
    place(PARIS, "Paris", 48.85341, 2.3488, "P", "PPLC", "FR", "11", 2138551, "باريس"),
    place(ZERO_POINT, "Zero Point", 0.0, 0.0, "P", "PPL", None, None, 100),
    place(EASTERN_EDGE, "Eastern Edge", 51.0, 179.96, "P", "PPL", "RU", "99", 10),
    place(WESTERN_EDGE, "Western Edge", 51.0, -179.9, "P", "PPL", "RU", "99", 10),
]
# The soft-deleted ones: in the tables, never in an answer.
INACTIVE = {OLD_TUNIS}
for _place in PLACES:
    _place["is_active"] = _place["geoname_id"] not in INACTIVE

# (id, geoname id, language, name, preferred, short, colloquial, historic)
NAMES: list[tuple[int, int, str, str, bool, bool, bool, bool]] = [
    (1, TUNIS_CITY, "ar", "تونس العاصمة", False, False, False, False),
    (2, TUNIS_CITY, "ar", "تونس", True, False, False, False),
    (3, TUNIS_CITY, "en", "Tunis", True, False, False, False),
    (4, TUNISIA, "ar", "تونس", True, False, False, False),
    (5, TUNISIA, "ar", "الجمهورية التونسية", False, False, False, False),
    (6, TUNISIA, "en", "Tunisia", True, False, False, False),
    (7, TUNIS_GOVERNORATE, "ar", "ولاية تونس", True, False, False, False),
    (8, TUNIS_GOVERNORATE, "en", "Tunis Governorate", False, False, False, False),
    (9, HAMMAM_LIF, "ar", "حمام الأنف", True, False, False, False),
    (10, HAMMAM_LIF, "en", "Hammam Lif", False, False, False, False),
    # Arabic letters win: a Latin spelling filed under "ar" is a name, not the label.
    (11, SFAX, "ar", "Sfaqis", True, False, False, False),
    (12, SFAX, "ar", "صفاقس", False, False, False, False),
    (13, SFAX, "fr", "Quetzalcoatl", True, False, False, False),
    (14, MECCA_CITY, "ar", "مكة", False, True, False, False),
    (15, MECCA_CITY, "ar", "مكّة", False, False, True, False),
    (16, MECCA_CITY, "ar", "مكة المكرمة", True, False, False, False),
    (17, MECCA_CITY, "en", "Mecca", True, False, False, False),
    (18, MECCA_CITY, "en", "Makkah al Mukarramah", False, False, False, False),
    (19, MECCA_REGION, "ar", "مكة المكرّمة", True, False, False, False),
    (20, MECCA_REGION, "en", "Makkah Province", False, False, False, False),
    (21, MEDINA, "ar", "المدينة", False, False, False, True),
    (22, MEDINA, "ar", "المدينة المنورة", False, False, False, False),
    (23, MEDINA, "en", "Medina", True, False, False, False),
    (24, RIYADH, "ar", "الرياض", True, False, False, False),
    (25, RIYADH, "en", "Riyadh", True, False, False, False),
    (26, PARIS, "ar", "باريس", True, False, False, False),
    (27, PARIS, "en", "Paris", True, False, False, False),
    (28, SMALLTOWN, "en", "Small Town", True, False, False, False),
    (29, SAUDI_ARABIA, "ar", "السعودية", False, True, False, False),
    (30, SAUDI_ARABIA, "ar", "المملكة العربية السعودية", True, False, False, False),
    (31, SAUDI_ARABIA, "en", "Saudi Arabia", True, False, False, False),
    (32, OLD_TUNIS, "ar", "تونس القديمة", True, False, False, False),
    (33, RIYADH_REGION, "ar", "منطقة الرياض", True, False, False, False),
]

# Names of other kinds, which a dump carries and the import drops.
NOISE_NAMES: list[tuple[int, int, str, str]] = [
    (101, TUNIS_CITY, "link", "https://en.wikipedia.org/wiki/Tunis"),
    (102, TUNIS_CITY, "wkdt", "Q3572"),
    (103, TUNIS_CITY, "abbr", "TUN"),
    (104, TUNIS_CITY, "de", "Tunis"),
    (105, 999, "ar", "مكان غير موجود"),
]

# (parent, child, type): the pair of a place that is not imported, and a repeated one.
HIERARCHY: list[tuple[int, int, str]] = [
    (TUNISIA, TUNIS_GOVERNORATE, "ADM"),
    (TUNIS_GOVERNORATE, TUNIS_CITY, ""),
    (TUNIS_GOVERNORATE, HAMMAM_LIF, "ADM"),
    (MECCA_REGION, MECCA_CITY, "ADM"),
]
NOISE_HIERARCHY: list[tuple[int, int, str]] = [
    (TUNISIA, 9999999, "ADM"),
    (TUNISIA, TUNIS_GOVERNORATE, "ADM"),
]

# Rows of the dump that the import leaves out: a lake, a spot, a mountain.
NOISE_PLACES = [
    place(3000001, "Lac de Tunis", 36.8, 10.2, "H", "LK", "TN", "36", 0),
    place(3000002, "Tunis Airport", 36.85, 10.22, "S", "AIRP", "TN", "36", 0),
    place(3000003, "Jebel Tunis", 36.7, 10.1, "T", "MT", "TN", "36", 0),
]

# ISO, ISO3, numeric, fips, country, capital, area, population, continent, tld,
# currency code, currency name, phone, postal format, postal regex, languages,
# geoname id, neighbours, equivalent fips
COUNTRIES = [
    ("TN", "TUN", "788", "TS", "Tunisia", "Tunis", "163610", "11565204", "AF", ".tn", "TND"),
    ("SA", "SAU", "682", "SA", "Saudi Arabia", "Riyadh", "1960582", "25731776", "AS", ".sa", "SAR"),
    ("FR", "FRA", "250", "FR", "France", "Paris", "547030", "64768389", "EU", ".fr", "EUR"),
]
COUNTRY_TAILS = {
    "TN": ("Dinar", "216", "####", r"^(\d{4})$", "ar-TN,fr", str(TUNISIA), "DZ,LY", ""),
    "SA": ("Rial", "966", "#####", r"^(\d{5})$", "ar-SA", str(SAUDI_ARABIA), "QA,OM,IQ", ""),
    "FR": ("Euro", "33", "#####", r"^(\d{5})$", "fr-FR,br,co", str(FRANCE), "CH,DE,BE", ""),
}


def flag(iso2: str) -> str:
    """The flag as the two regional-indicator letters of the country code."""
    return "".join(chr(127397 + ord(letter)) for letter in iso2)


async def load_world(session: AsyncSession) -> None:
    """Insert the world through the models; the caller's transaction is rolled back after."""
    for item in PLACES:
        session.add(
            GeoName(
                **item,
                location_geom=func.ST_SetSRID(
                    func.ST_MakePoint(item["longitude"], item["latitude"]), 4326
                ),
            )
        )
    for alt_id, geoname_id, language, name, preferred, short, colloquial, historic in NAMES:
        session.add(
            GeoAlternateName(
                alternate_name_id=alt_id,
                geoname_id=geoname_id,
                iso_language=language,
                alternate_name=name,
                is_preferred=preferred,
                is_short=short,
                is_colloquial=colloquial,
                is_historic=historic,
            )
        )
    for head in COUNTRIES:
        tail = COUNTRY_TAILS[head[0]]
        session.add(
            GeoCountryInfo(
                iso2=head[0],
                iso3=head[1],
                iso_numeric=int(head[2]),
                fips=head[3],
                country_name=head[4],
                capital=head[5],
                area_km2=float(head[6]),
                population=int(head[7]),
                continent=head[8],
                top_level_domain=head[9],
                currency_code=head[10],
                currency_name=tail[0],
                phone_prefix=tail[1],
                postal_code_format=tail[2],
                languages=tail[4],
                geoname_id=int(tail[5]),
                neighbours=tail[6],
                flag_emoji=flag(head[0]),
            )
        )
    await session.flush()


# ─── The same world as GeoNames dump files ──────────────────────────


def places_row(item: dict[str, Any]) -> str:
    """One line of allCountries.txt: 19 tab-separated columns."""
    population = "" if item["population"] is None else str(item["population"])
    columns = [
        str(item["geoname_id"]),
        item["name"],
        item["name"],
        "",
        str(item["latitude"]),
        str(item["longitude"]),
        item["feature_class"],
        item["feature_code"],
        item["country_code"] or "",
        "",
        item["admin1_code"] or "",
        "",
        "",
        "",
        population,
        "",
        "",
        "Africa/Tunis",
        "2024-05-01",
    ]
    return "\t".join(columns)


def names_row(alt_id: int, geoname_id: int, language: str, name: str, *flags: bool) -> str:
    """One line of alternateNamesV2.txt: 10 tab-separated columns."""
    marks = ["1" if flag_set else "" for flag_set in flags] + [""] * (4 - len(flags))
    return "\t".join([str(alt_id), str(geoname_id), language, name, *marks, "", ""])


def dump_files(
    *,
    places: list[dict[str, Any]] | None = None,
    names: list[tuple[int, int, str, str, bool, bool, bool, bool]] | None = None,
    hierarchy: list[tuple[int, int, str]] | None = None,
) -> dict[str, str]:
    """The text of each dump file, by name; the arguments replace parts of the world."""
    places = PLACES if places is None else places
    names = NAMES if names is None else names
    hierarchy = HIERARCHY if hierarchy is None else hierarchy
    countries = []
    for head in COUNTRIES:
        tail = COUNTRY_TAILS[head[0]]
        countries.append("\t".join([*head, *tail]))
    return {
        "allCountries.txt": "\n".join([places_row(item) for item in [*NOISE_PLACES, *places]])
        + "\n",
        "alternateNamesV2.txt": "\n".join(
            [names_row(*row) for row in names]
            + [
                names_row(alt_id, geoname_id, language, name)
                for alt_id, geoname_id, language, name in NOISE_NAMES
            ]
        )
        + "\n",
        "hierarchy.txt": "\n".join(
            "\t".join(map(str, row)) for row in [*hierarchy, *NOISE_HIERARCHY]
        )
        + "\n",
        "countryInfo.txt": "# GeoNames.org Country Information\n"
        "# ================================\n"
        "#ISO\tISO3\tISO-Numeric\tfips\tCountry\tCapital\n" + "\n".join(countries) + "\n\n",
    }


def write_dump(cache: Path, **parts: Any) -> None:
    """Write the dump files as the download cache holds them, each with its `.done` marker."""
    files = dump_files(**parts)
    cache.mkdir(parents=True, exist_ok=True)
    for archive, member in (
        ("allCountries.zip", "allCountries.txt"),
        ("alternateNamesV2.zip", "alternateNamesV2.txt"),
        ("hierarchy.zip", "hierarchy.txt"),
    ):
        with zipfile.ZipFile(cache / archive, "w") as zipped:
            zipped.writestr(member, files[member])
            zipped.writestr("readme.txt", "not data")
        (cache / f"{archive}.done").touch()
    (cache / "countryInfo.txt").write_text(files["countryInfo.txt"])
    (cache / "countryInfo.txt.done").touch()


def write_postal_codes(cache: Path, text: str) -> None:
    """Write postalCodes.zip, whose member is allCountries.txt as in the real download."""
    with zipfile.ZipFile(cache / "postalCodes.zip", "w") as zipped:
        zipped.writestr("allCountries.txt", text)
        zipped.writestr("readme.txt", "not data")
    (cache / "postalCodes.zip.done").touch()
