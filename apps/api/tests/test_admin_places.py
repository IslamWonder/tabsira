"""The GeoNames view: read-only, searchable, and cheap on a table of millions of rows."""

from __future__ import annotations

import re

from sqlalchemy import text


async def add_places(db_session):
    await db_session.execute(
        text(
            """
            INSERT INTO geodata.geonames
                (geoname_id, name, ar_name, country_code, feature_class, feature_code, population)
            VALUES
                (1, 'Tunis', 'تونس', 'TN', 'P', 'PPLC', 700000),
                (2, 'Tunisia', 'الجمهورية التونسية', 'TN', 'A', 'PCLI', 11000000),
                (3, 'Cairo', 'القاهرة', 'EG', 'P', 'PPLC', 9000000),
                (4, '100%_odd', NULL, 'XX', 'P', 'PPL', 1)
            """
        )
    )


def total_of(page):
    found = re.search(r"of (\d+) items", page.text)
    assert found
    return int(found.group(1))


async def test_places_are_listed_by_population_with_the_columns_a_person_needs(admin, db_session):
    http, _ = admin
    await add_places(db_session)

    page = await http.get("/admin/geo-name/list")

    assert page.status_code == 200
    body = page.text
    assert body.index("Tunisia") < body.index("Cairo") < body.index("Tunis<")
    for header in ("Geoname id", "Ar name", "Country code", "Feature code", "Population"):
        assert header in body
    # The geometry is a binary value no one reads, and is not a column here.
    assert "location_geom" not in body
    assert "Location geom" not in body


async def test_a_search_in_latin_letters_reads_the_name_and_ignores_case(admin, db_session):
    http, _ = admin
    await add_places(db_session)

    page = await http.get("/admin/geo-name/list?search=TUNIS")

    body = page.text.split("<tbody>")[-1]
    assert "Tunis<" in body
    assert "Tunisia" in body
    assert "Cairo" not in body


async def test_a_search_in_arabic_letters_reads_the_arabic_name(admin, db_session):
    http, _ = admin
    await add_places(db_session)

    page = await http.get("/admin/geo-name/list?search=القاهرة")

    body = page.text.split("<tbody>")[-1]
    assert "Cairo" in body
    assert "Tunis<" not in body


async def test_a_wildcard_character_in_a_search_is_a_letter_not_a_pattern(admin, db_session):
    http, _ = admin
    await add_places(db_session)

    percent = await http.get("/admin/geo-name/list?search=%25")
    underscore = await http.get("/admin/geo-name/list?search=_odd")

    assert "100%_odd" in percent.text
    assert "Tunis<" not in percent.text.split("<tbody>")[-1]
    assert "100%_odd" in underscore.text
    assert "Cairo" not in underscore.text.split("<tbody>")[-1]


async def test_a_place_has_a_page_with_its_coordinates_and_zone(admin, db_session):
    http, _ = admin
    await add_places(db_session)
    await db_session.execute(
        text(
            "UPDATE geodata.geonames SET latitude = 36.8, longitude = 10.18, "
            "timezone = 'Africa/Tunis' WHERE geoname_id = 1"
        )
    )

    page = await http.get("/admin/geo-name/details/1")

    assert page.status_code == 200
    for shown in ("Tunis", "تونس", "Africa/Tunis", "36.8", "10.18"):
        assert shown in page.text


async def test_the_total_is_the_planners_estimate_until_the_list_is_narrowed(admin, db_session):
    http, _ = admin
    await add_places(db_session)
    await db_session.execute(text("ANALYZE geodata.geonames"))
    await db_session.execute(
        text("INSERT INTO geodata.geonames (geoname_id, name) VALUES (5, 'Unanalysed')")
    )

    whole = await http.get("/admin/geo-name/list")
    sorted_ = await http.get("/admin/geo-name/list?sortBy=name&sort=asc")
    searched = await http.get("/admin/geo-name/list?search=n")
    filtered = await http.get("/admin/geo-name/list?is_active=true")

    # The estimate knows four rows; a narrowed list is counted exactly, and sees the fifth.
    assert total_of(whole) == 4
    assert total_of(sorted_) == 4
    assert total_of(searched) == 3
    assert total_of(filtered) == 5


async def test_before_the_table_is_analysed_the_total_is_counted_exactly(admin, db_session):
    http, _ = admin
    await add_places(db_session)

    assert total_of(await http.get("/admin/geo-name/list")) == 4


async def test_places_cannot_be_created_edited_deleted_or_exported(admin, db_session):
    http, _ = admin
    await add_places(db_session)

    assert (await http.get("/admin/geo-name/create")).status_code == 403
    assert (await http.get("/admin/geo-name/edit/1")).status_code == 403
    assert (await http.get("/admin/geo-name/export/csv")).status_code == 403
    token = re.search(
        r'csrf-token" content="([^"]+)"', (await http.get("/admin/geo-name/list")).text
    )
    assert token
    assert (
        await http.delete("/admin/geo-name/delete?pks=1", headers={"X-CSRF-Token": token.group(1)})
    ).status_code == 403
