from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from mockdata import catalogue
from mockdata.catalogue import Photo


def photo(name: str, category: str = "cat", pid: int = 1) -> Photo:
    return Photo(pid, name, category, 10, 10)


@pytest.mark.parametrize(
    "name",
    [
        "boy-under-the-bridge.jpg",
        "young-tourist-women-in-the-city.jpg",
        "children_writing.jpg",
        "mongolian-family-with-horse.jpg",
        "strawberry-in-hand.jpg",
        "SelfieOnTheStreet.jpg",
        "portrait-of-a-man.jpg",
        "roasted-bacon.jpg",
        "crowd.jpg",
        "face.jpg",
    ],
)
def test_person_or_unsuitable_filenames_are_dropped(name: str) -> None:
    assert not catalogue.keep(photo(name, "city"))


def test_kid_category_and_unlisted_categories_are_dropped() -> None:
    assert not catalogue.keep(photo("toys.jpg", "kid"))
    assert not catalogue.keep(photo("engine.jpg", "car"))


@pytest.mark.parametrize(
    ("name", "category", "kept"),
    [
        ("cat-portrait.jpg", "cat", True),
        ("black-dog-face.jpg", "dog", True),
        ("lion-portrait.jpg", "nature", False),
        ("portrait.jpg", "nature", False),
        ("cat_eyes.jpg", "cat", True),
        ("cat-with-man.jpg", "cat", False),
        ("red-roses.jpg", "flower", True),
    ],
)
def test_portrait_allowed_only_for_animals(name: str, category: str, kept: bool) -> None:
    assert catalogue.keep(photo(name, category)) is kept


def test_animal_word_lets_a_portrait_through_in_any_category() -> None:
    assert catalogue.keep(photo("kitten-portrait.jpg", "nature"))


def test_words_split_camel_case_and_digits() -> None:
    assert catalogue.words("RedCat_12-sleeping.jpg") == ["red", "cat", "sleeping"]


def test_filter_sorts_by_id() -> None:
    kept = catalogue.filter_photos([photo("b.jpg", "cat", 5), photo("a.jpg", "cat", 2)])
    assert [p.id for p in kept] == [2, 5]


def test_url_fits_the_key_column() -> None:
    url = photo("a.jpg", "cat", 724).url
    assert url == "https://placepix.net/id/724/1080/1080"
    assert len(url) <= catalogue.MAX_KEY_LENGTH


def fake_client(missing_from: int) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/categories":
            return httpx.Response(200, json={"detailed": [{"count": 3}, {"count": 2}]})
        n = int(path.rsplit("/", 1)[1])
        if n >= missing_from:
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={"id": n, "filename": f"f{n}.jpg", "category": "cat", "width": 5, "height": 6},
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_collects_every_photo_with_a_polite_delay() -> None:
    delays: list[float] = []
    photos = catalogue.fetch_catalogue(fake_client(99), delay=0.5, sleep=delays.append)
    assert [p.id for p in photos] == [1, 2, 3, 4, 5]
    assert delays == [0.5] * 5


def test_fetch_stops_after_a_gap_of_missing_ids() -> None:
    photos = catalogue.fetch_catalogue(fake_client(3), delay=0, sleep=lambda _: None, max_gap=2)
    assert [p.id for p in photos] == [1, 2]


def test_fetch_fails_loudly_when_categories_fail() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError):
        catalogue.fetch_catalogue(client)


def test_cache_is_used_until_refreshed(tmp_path: Path) -> None:
    cache = tmp_path / "sub" / "c.json"
    calls: list[int] = []

    def fetch() -> list[Photo]:
        calls.append(1)
        return [photo("a.jpg")]

    assert catalogue.get_catalogue(cache, False, fetch) == [photo("a.jpg")]
    catalogue.get_catalogue(cache, False, fetch)
    assert len(calls) == 1
    catalogue.get_catalogue(cache, True, fetch)
    assert len(calls) == 2
