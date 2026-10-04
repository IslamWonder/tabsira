"""The quranpedia client: verified dumps, a polite request rate, the changes feed, one verse."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from src.scripture import files as source_files
from src.scripture.quranpedia import (
    USER_AGENT,
    ChangedAyah,
    Manifest,
    QuranpediaClient,
    QuranpediaError,
    cached_dump_files,
    dump_url,
    fetch_dump_files,
    new_http_client,
)
from tests.scripture_fixtures import fixture_path, load_json
from tests.scripture_http import FakeQuranpedia, dump_routes, json_response, manifest_for


def _row(surah: int = 30, ayah: int = 50, refetch: str | None = None) -> ChangedAyah:
    return ChangedAyah(
        mushaf=2,
        surah=surah,
        ayah=ayah,
        changed_at="2026-10-04 16:51:13",
        refetch=refetch or f"/v1/mushafs/2/{surah}/{ayah}",
    )


def test_the_client_names_the_project_and_no_person():
    http = new_http_client()

    assert http.headers["User-Agent"] == USER_AGENT == "tabsira/0.1 (+https://tabsira.me)"
    assert "@" not in USER_AGENT
    assert dump_url("surahs.json.gz") == "https://api.quranpedia.net/dumps/surahs.json.gz"


async def test_both_dump_files_are_downloaded_once_and_verified(tmp_path):
    fake = FakeQuranpedia(dump_routes())
    client = fake.client()

    first = await fetch_dump_files(client, tmp_path)
    second = await fetch_dump_files(client, tmp_path)

    downloads = [r.url.path for r in fake.requests if r.url.path != "/dumps/manifest.json"]
    assert downloads == ["/dumps/mushafs-2.json.gz", "/dumps/surahs.json.gz"]
    assert first == second
    assert first.version == "2026-10-03"
    assert first.mushaf == tmp_path / "quranpedia" / "2026-10-03" / "mushafs-2.json.gz"
    assert source_files.file_sha256(first.mushaf) == first.mushaf_sha256
    assert source_files.file_sha256(first.surahs) == first.surahs_sha256
    assert cached_dump_files(tmp_path) == first


async def test_a_dump_file_that_does_not_match_the_manifest_is_refused(tmp_path):
    routes = dump_routes()
    routes["/dumps/surahs.json.gz"] = httpx.Response(200, content=b"tampered")
    client = FakeQuranpedia(routes).client()

    with pytest.raises(source_files.SourceFileError, match=r"surahs\.json\.gz has sha256"):
        await fetch_dump_files(client, tmp_path)

    assert not (tmp_path / "quranpedia" / "2026-10-03" / "surahs.json.gz").exists()


async def test_the_cache_answers_with_the_newest_dump_that_still_verifies(tmp_path):
    assert cached_dump_files(tmp_path) is None

    older = await fetch_dump_files(FakeQuranpedia(dump_routes("2026-10-02")).client(), tmp_path)
    newer = await fetch_dump_files(FakeQuranpedia(dump_routes("2026-10-03")).client(), tmp_path)
    (tmp_path / "quranpedia" / "2026-10-04").mkdir()

    assert cached_dump_files(tmp_path) == newer
    assert cached_dump_files(tmp_path, "2026-10-02") == older

    newer.surahs.write_bytes(b"corrupted")
    assert cached_dump_files(tmp_path) == older


def test_a_manifest_without_the_file_is_an_error():
    manifest = Manifest.model_validate(manifest_for({"other.json.gz": b"x"}))

    with pytest.raises(QuranpediaError, match=r"lists no mushafs-2\.json\.gz"):
        manifest.file("mushafs-2.json.gz")


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (httpx.Response(429, json={"error": "Too many requests."}), "answered 429"),
        (httpx.Response(200, content=b"<html>"), "unexpected body"),
    ],
)
async def test_an_error_or_an_unexpected_answer_is_reported(answer, message):
    client = FakeQuranpedia({"/dumps/manifest.json": answer}).client()

    with pytest.raises(QuranpediaError, match=message):
        await client.manifest()


async def test_a_network_failure_is_reported_without_its_details():
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = FakeQuranpedia({"/dumps/manifest.json": fail}).client()

    with pytest.raises(QuranpediaError, match="failed: ConnectTimeout"):
        await client.manifest()


async def test_requests_are_spaced_to_stay_under_the_rate_limit():
    now = [100.0]
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    fake = FakeQuranpedia(dump_routes())
    client = QuranpediaClient(
        httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
        interval=0.6,
        sleep=sleep,
        clock=lambda: now[0],
    )

    await client.manifest()
    now[0] += 0.2
    await client.manifest()
    now[0] += 5.0
    await client.manifest()

    assert waits == [pytest.approx(0.4)]
    assert len(fake.requests) == 3


async def test_the_changes_feed_is_read_for_verses_only():
    payload = load_json("quranpedia-changes.json")
    fake = FakeQuranpedia({"/v1/changes?since=2026-08-08": json_response(payload)})

    feed = await fake.client().changes(date(2026, 8, 8))

    assert feed.since == "2026-08-08"
    assert feed.ayahs.count == len(feed.ayahs.rows) == 3
    assert feed.ayahs.rows[0].refetch == payload["changes"]["ayahs"]["rows"][0]["refetch"]
    assert feed.ayahs.rows[0].surah == int(payload["changes"]["ayahs"]["rows"][0]["surah"])


@pytest.mark.parametrize("body", [b"not json", b"{}", b'{"since": 1, "until": 2, "changes": []}'])
async def test_a_changes_feed_that_cannot_be_read_is_an_error(body):
    fake = FakeQuranpedia({"/v1/changes": httpx.Response(200, content=body)})

    with pytest.raises(QuranpediaError, match="unexpected body"):
        await fake.client().changes(date(2026, 10, 3))


async def test_one_changed_verse_is_refetched_by_its_path():
    body = fixture_path("quranpedia-ayah-2-30-50.json").read_bytes()
    fake = FakeQuranpedia({"/v1/mushafs/2/30/50": httpx.Response(200, content=body)})

    verse = await fake.client().ayah(_row())

    assert verse.text == json.loads(body)["text"]
    assert verse.id == 65709
    assert fake.requests[0].url == "https://api.quranpedia.net/v1/mushafs/2/30/50"


@pytest.mark.parametrize(
    "row",
    [
        _row(refetch="/v1/mushafs/1/30/50"),
        _row(refetch="https://elsewhere.example/v1/mushafs/2/30/50"),
        _row(ayah=49, refetch="/v1/mushafs/2/30/50"),
    ],
)
async def test_a_refetch_path_for_another_mushaf_or_verse_is_refused(row):
    fake = FakeQuranpedia({})

    with pytest.raises(QuranpediaError, match="unexpected refetch path"):
        await fake.client().ayah(row)

    assert fake.requests == []


@pytest.mark.parametrize("change", [{"number": 49}, {"text": ""}])
async def test_a_refetched_verse_that_is_not_the_one_asked_for_is_refused(change):
    payload = {**load_json("quranpedia-ayah-2-30-50.json"), **change}
    fake = FakeQuranpedia({"/v1/mushafs/2/30/50": json_response(payload)})

    with pytest.raises(QuranpediaError, match="another verse or an empty text"):
        await fake.client().ayah(_row())


def test_source_files_are_checked_and_written_whole(tmp_path):
    path = tmp_path / "deep" / "file.bin"

    with pytest.raises(source_files.SourceFileError, match="is missing"):
        source_files.require_verified(path, "0" * 64)

    source_files.write_atomically(path, b"abc")
    digest = source_files.bytes_sha256(b"abc")

    assert source_files.require_verified(path, digest) == path
    assert source_files.is_verified(path, digest)
    assert not source_files.is_verified(tmp_path / "absent", digest)
    assert sorted(p.name for p in path.parent.iterdir()) == ["file.bin"]
    with pytest.raises(source_files.SourceFileError, match="has sha256"):
        source_files.require_verified(path, "0" * 64)
