"""Place search, reverse lookup and countries, on the small world of tests/geo_dataset.py."""

from __future__ import annotations

import pytest

from src.services import geo_service
from tests import geo_dataset as world_data
from tests.geo_dataset import (
    EASTERN_EDGE,
    HAMMAM_LIF,
    MECCA,
    MECCA_CITY,
    MECCA_REGION,
    MEDINA,
    SFAX,
    SMALLTOWN,
    TUNIS,
    TUNIS_CITY,
    TUNIS_ELSEWHERE,
    TUNIS_GOVERNORATE,
    TUNISIA,
    ZERO_POINT,
)


@pytest.fixture
async def world(db_session):
    await world_data.load_world(db_session)
    return db_session


def ids(hits):
    return [hit.geoname_id for hit in hits]


# ─── Search ─────────────────────────────────────────────────────────


async def test_an_arabic_name_finds_the_exact_matches_first_by_population(world):
    hits = await geo_service.search_places(world, "تونس")

    # The country and the capital are both called تونس; the larger comes first. The
    # governorate is only similar (ولاية تونس), so it follows.
    assert ids(hits)[:3] == [TUNISIA, TUNIS_CITY, TUNIS_GOVERNORATE]


async def test_a_latin_name_ranks_exact_then_prefix_then_similar(world):
    hits = await geo_service.search_places(world, "Tunis")

    # Exact: the capital before the hamlet of the same name. Prefix: Tunisia and the
    # governorate by population. A place that is soft-deleted never appears.
    assert ids(hits)[:4] == [TUNIS_CITY, TUNIS_ELSEWHERE, TUNISIA, TUNIS_GOVERNORATE]
    assert world_data.OLD_TUNIS not in ids(hits)


@pytest.mark.parametrize(
    "query",
    ["تونس", "تُونِس", "  تونس ", "تـونس"],
)
async def test_arabic_vowel_marks_stretching_and_spaces_do_not_change_the_answer(world, query):
    assert ids(await geo_service.search_places(world, query))[:2] == [TUNISIA, TUNIS_CITY]


@pytest.mark.parametrize("query", ["مكة", "مكه", "mecca", "MECCA", "Makkah"])
async def test_the_spellings_of_one_name_find_the_same_place(world, query):
    assert ids(await geo_service.search_places(world, query))[0] == MECCA_CITY


@pytest.mark.parametrize("query", ["مكة المكرمة", "مكه المكرمه", "مَكَّةَ المُكَرَّمَة"])
async def test_a_full_name_finds_the_city_and_the_region_that_share_it(world, query):
    # The region is called the same, and is the more populous of the two.
    assert ids(await geo_service.search_places(world, query))[:2] == [MECCA_REGION, MECCA_CITY]


@pytest.mark.parametrize("query", ["المدينة المنورة", "المدينه المنوره", "Medina", "Al Madinah"])
async def test_a_place_is_found_by_any_of_its_names_but_labelled_by_the_best_arabic_one(
    world, query
):
    hits = await geo_service.search_places(world, query)

    assert hits[0].geoname_id == MEDINA
    assert hits[0].label == "المدينة المنورة"


@pytest.mark.parametrize("query", ["Hammam Lif", "hammam-lif", "Hammam-Lif", "حمام الانف"])
async def test_hyphens_spaces_and_the_hamza_do_not_matter(world, query):
    assert ids(await geo_service.search_places(world, query))[0] == HAMMAM_LIF


async def test_a_prefix_and_a_misspelling_find_the_place(world):
    assert HAMMAM_LIF in ids(await geo_service.search_places(world, "Hamm"))
    assert HAMMAM_LIF in ids(await geo_service.search_places(world, "حمام"))
    assert TUNIS_CITY in ids(await geo_service.search_places(world, "Tunes"))
    assert ids(await geo_service.search_places(world, "Mecka"))[:1] == [MECCA_CITY]


async def test_similar_names_are_looked_for_only_when_the_exact_and_prefix_matches_are_few(world):
    from src.models import GeoName

    world.add(
        GeoName(
            geoname_id=7_000_001,
            name="Tunes",
            latitude=37.1,
            longitude=-8.2,
            feature_class="P",
            feature_code="PPL",
            country_code="PT",
            population=6837,
        )
    )
    await world.flush()

    enough = await geo_service.search_places(world, "Tunes", limit=1)
    room = await geo_service.search_places(world, "Tunes", limit=5)

    # The one exact match fills the limit: Tunis, which is only similar, is not even looked for.
    assert ids(enough) == [7_000_001]
    assert ids(room)[0] == 7_000_001
    assert TUNIS_CITY in ids(room)


async def test_a_misspelling_of_four_letters_is_enough_for_a_similar_name(world):
    # "unis" is not the start of any name, and is four letters, the shortest that is matched
    # by similarity; a shorter piece would be matched by prefix only.
    assert TUNIS_CITY in ids(await geo_service.search_places(world, "unis"))
    assert await geo_service.search_places(world, "uni") == []


async def test_only_arabic_and_english_names_are_searched(world):
    # Sfax has a French name in the tables; the import keeps no other language, and a
    # query in one finds nothing even if a row were there.
    assert await geo_service.search_places(world, "Quetzalcoatl") == []


async def test_a_latin_spelling_filed_as_arabic_is_a_name_but_not_the_label(world):
    hits = await geo_service.search_places(world, "Sfaqis")

    assert ids(hits)[:1] == [SFAX]
    assert hits[0].name_ar == "صفاقس"
    assert hits[0].label == "صفاقس"


@pytest.mark.parametrize("query", ["%%", "_%", "!!", "--", " . "])
async def test_wildcards_and_punctuation_match_nothing_instead_of_everything(world, query):
    assert await geo_service.search_places(world, query) == []


async def test_the_limit_is_respected(world):
    hits = await geo_service.search_places(world, "Tunis", limit=2)

    assert ids(hits) == [TUNIS_CITY, TUNIS_ELSEWHERE]


async def test_a_hit_carries_its_names_position_region_and_country(world):
    hit = (await geo_service.search_places(world, "Tunis"))[0]

    assert hit.model_dump(mode="json") == {
        "geoname_id": TUNIS_CITY,
        "name": "Tunis",
        "name_ar": "تونس",
        "label": "تونس",
        "feature_class": "P",
        "feature_code": "PPLC",
        "population": 693210,
        "latitude": 36.81897,
        "longitude": 10.16579,
        # GeoJSON: longitude first.
        "location": {"type": "Point", "coordinates": [10.16579, 36.81897]},
        "admin_area": {
            "geoname_id": TUNIS_GOVERNORATE,
            "name": "Gouvernorat de Tunis",
            "name_ar": "ولاية تونس",
            "label": "ولاية تونس",
        },
        "country": {"iso2": "TN", "name": "Tunisia", "name_ar": "تونس", "label": "تونس"},
    }


async def test_a_place_without_an_arabic_name_is_labelled_in_latin(world):
    hit = (await geo_service.search_places(world, "Smalltown"))[0]

    assert (hit.geoname_id, hit.name_ar, hit.label) == (SMALLTOWN, None, "Smalltown")
    # A name found only in an English alternate name still finds it.
    assert ids(await geo_service.search_places(world, "small town"))[0] == SMALLTOWN


async def test_a_missing_region_or_country_is_null_not_an_error(world):
    paris = (await geo_service.search_places(world, "باريس"))[0]
    hamlet = next(
        hit
        for hit in await geo_service.search_places(world, "Tunis")
        if hit.geoname_id == TUNIS_ELSEWHERE
    )
    sfax = (await geo_service.search_places(world, "Sfax"))[0]
    region = next(
        hit
        for hit in await geo_service.search_places(world, "Tunis Governorate")
        if hit.geoname_id == TUNIS_GOVERNORATE
    )
    country = next(
        hit
        for hit in await geo_service.search_places(world, "Tunisia")
        if hit.geoname_id == TUNISIA
    )

    # France is in the country table but its own row is not: the name stays Latin.
    assert paris.admin_area is None
    assert paris.country is not None
    assert (paris.country.iso2, paris.country.name_ar, paris.country.label) == (
        "FR",
        None,
        "France",
    )
    # No country row at all.
    assert hamlet.country is None
    # A region the tables do not hold.
    assert sfax.admin_area is None
    assert sfax.country is not None
    assert sfax.country.iso2 == "TN"
    # A region is not its own region, a country has none.
    assert region.admin_area is None
    assert country.admin_area is None


async def test_a_place_without_coordinates_is_not_offered(world):
    from sqlalchemy import update

    from src.models import GeoName

    await world.execute(
        update(GeoName)
        .where(GeoName.geoname_id == TUNIS_CITY)
        .values(latitude=None, longitude=None)
    )

    assert TUNIS_CITY not in ids(await geo_service.search_places(world, "Tunis"))


# ─── Reverse ────────────────────────────────────────────────────────


async def test_the_nearest_settlement_is_found_with_its_region_and_country(world):
    result = await geo_service.nearest_place(world, *TUNIS)

    # The neighbourhood and the soft-deleted town are nearer, and are not candidates.
    assert result.place is not None
    assert result.place.geoname_id == TUNIS_CITY
    assert 1_900 <= result.place.distance_m <= 2_100
    assert (result.place.label, result.place.location.coordinates) == ("تونس", (10.16579, 36.81897))
    assert result.admin_area is not None
    assert result.admin_area.label == "ولاية تونس"
    assert result.country is not None
    assert result.country.label == "تونس"


async def test_mecca_is_found_from_a_point_in_its_cell(world):
    result = await geo_service.nearest_place(world, *MECCA)

    assert result.place is not None
    assert (result.place.geoname_id, result.place.label) == (MECCA_CITY, "مكة المكرمة")
    assert result.place.distance_m < 1_000
    assert result.admin_area is not None
    assert result.admin_area.geoname_id == MECCA_REGION
    assert result.country is not None
    assert result.country.label == "المملكة العربية السعودية"


async def test_a_coordinate_of_zero_is_a_place_on_the_map(world):
    result = await geo_service.nearest_place(world, 0, 0)

    assert result.place is not None
    assert (result.place.geoname_id, result.place.distance_m) == (ZERO_POINT, 0)
    assert result.place.location.coordinates == (0.0, 0.0)
    assert (result.admin_area, result.country) == (None, None)
    # Zero latitude or zero longitude alone is as good as any other value.
    assert (await geo_service.nearest_place(world, 0.0, 0.001)).place is not None


async def test_nothing_in_range_is_an_empty_answer(world):
    result = await geo_service.nearest_place(world, -40, -30)

    assert (result.place, result.admin_area, result.country) == (None, None, None)


async def test_the_radius_decides_what_is_near(world):
    assert (await geo_service.nearest_place(world, *TUNIS, radius_m=1_000)).place is None
    near = await geo_service.nearest_place(world, *TUNIS, radius_m=5_000)
    assert near.place is not None
    assert near.place.geoname_id == TUNIS_CITY


async def test_a_historical_place_is_never_the_answer_even_when_it_is_the_nearest(world):
    result = await geo_service.nearest_place(world, 36.853, 10.323, radius_m=3_000)

    assert result.place is None


async def test_the_antimeridian_is_not_the_end_of_the_map(world):
    on_the_line = await geo_service.nearest_place(world, 51.0, 180)
    other_name = await geo_service.nearest_place(world, 51.0, -180)
    just_west = await geo_service.nearest_place(world, 51.0, -179.99)

    assert on_the_line.place is not None
    assert on_the_line.place.geoname_id == EASTERN_EDGE
    assert other_name == on_the_line
    # West of the line, the nearer of the two places is still the one across it.
    assert just_west.place is not None
    assert just_west.place.geoname_id == EASTERN_EDGE
    assert just_west.place.distance_m < 4_000


async def test_the_answer_says_nothing_about_the_point_asked(world):
    result = await geo_service.nearest_place(world, 36.80123, 10.18123)

    dumped = result.model_dump_json()
    assert "36.80123" not in dumped
    assert "10.18123" not in dumped


# ─── Countries ──────────────────────────────────────────────────────


async def test_countries_are_listed_by_name_with_their_arabic_name_when_known(world):
    countries = await geo_service.list_countries(world)

    assert [country.iso2 for country in countries] == ["FR", "SA", "TN"]
    france, saudi, tunisia = countries
    assert (france.name, france.name_ar, france.label) == ("France", None, "France")
    assert (saudi.name_ar, saudi.label) == ("المملكة العربية السعودية", "المملكة العربية السعودية")
    assert tunisia.model_dump() == {
        "iso2": "TN",
        "iso3": "TUN",
        "name": "Tunisia",
        "name_ar": "تونس",
        "label": "تونس",
        "capital": "Tunis",
        "continent": "AF",
        "flag_emoji": "🇹🇳",
        "population": 11565204,
    }
