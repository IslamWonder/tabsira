# 22 · Mock members to start the platform

**Phase:** 2 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-05 (Tunis)

The platform opens with about 1000 mock members living in real cities of the Arabic-speaking Muslim-majority countries, each with insights, posts, reactions, follows, comments and atlas entries, so the feed, the atlas and the camera discovery are alive on the first day (decision 63). Their photos are placepix.net's; their insights come from the real pipeline. Nothing on screen marks them as mock.

Two programs, two libraries and one file:

1. **The generator** (`tools/mockdata/`, its own uv project) reads the photo library and the GeoNames tables and writes `tabsira-mock-v<N>.json` to `../tabsira-data/mock/`. Its process step (task 23.4) runs the real pipeline over the placepix photos into `photo-library.json` and writes the posts' texts into `texts-library.json` and the file. Nothing of it is committed; the owners upload the file to their bucket (s3-v2) and regenerate it when retrieval changes.
2. **The importer** (`python -m src.cli.import_mock`, in `apps/api`) reads that file from a path or the bucket and writes the rows through the application's own services, so approximate places, public ids and photo rules are the ones members get. `--clean` removes every mock row.
3. **The file** holds references only: placepix ids, GeoNames ids, exact points, times, evidence ids (surah and ayah, collection and number) and the composed insight text. Never a verse or a hadith text.

| Step                                             | Status | Notes                                      |
| ------------------------------------------------ | ------ | ------------------------------------------ |
| Placepix photo addresses shown as is             | ✅     | task 23.1. Decision 63. Privacy review.    |
| Generator: catalogue, members, places, the graph | ✅     | task 23.2.                                 |
| Importer and `--clean`                           | ✅     | task 23.3.                                 |
| Real processing of the photos                    | ✅     | task 23.4, on the retrieval of 2026-10-05. |

**How we check it**

- A placepix key is returned as is by the public photo address, and no storage call (put, copy, exists, delete, reconcile) ever receives one (tested).
- The file contains no verse or hadith text: the scripture guard runs over every text field before it is written, and the importer refuses a file that fails it (tested).
- Every evidence id of the file exists in the store; a missing one skips that insight and is reported, never replaced (tested).
- No public answer carries a mock member's exact point; their atlas entries go through `geo/privacy.py` like any other (tested).
- `import_mock` twice imports nothing the second time; `--clean` leaves no row owned by a `@mock.tabsira.invalid` account and touches no other (tested).
- The importer refuses to run without `--i-understand`, and refuses the test database.

## The file, version 1

```json
{
  "version": 1,
  "seed": 42,
  "generated_at": "2026-10-05T10:00:00Z",
  "images": [
    {
      "placepix_id": 12,
      "url": "https://placepix.net/id/12/1080/1080",
      "width": 2636,
      "height": 1804,
      "filename": "camels.jpg",
      "category": "animal",
      "scene": { "labels": ["camel"], "ar": "جمال في الصحراء" },
      "insight": null
    }
  ],
  "members": [
    {
      "ref": "m0001",
      "handle": "",
      "display_name": "",
      "country": "TN",
      "city_geoname_id": 2464470,
      "joined_at": ""
    }
  ],
  "insights": [
    {
      "ref": "i00001",
      "member": "m0001",
      "image": 12,
      "created_at": "",
      "completed_at": "",
      "point": [10.18, 36.8]
    }
  ],
  "posts": [
    {
      "ref": "p00001",
      "insight": "i00001",
      "published_at": "",
      "reflection": null
    }
  ],
  "map_entries": [{ "insight": "i00001", "published_at": "" }],
  "follows": [{ "from": "m0001", "to": "m0002", "at": "" }],
  "reactions": [
    { "post": "p00001", "member": "m0002", "kind": "benefited", "at": "" }
  ],
  "comments": [
    {
      "ref": "c00001",
      "post": "p00001",
      "member": "m0003",
      "parent": null,
      "text": null,
      "at": ""
    }
  ]
}
```

`images[].insight` holds the pipeline's insight from the photo library (evidence ids, the reasons they were chosen, the composed text, the concept; the importer's `InsightBodyIn`), and only photos that gave one are in the file. Reflections and comment texts come from the texts library; one the guards refused stays `null` and the importer skips it. Points are GeoJSON order, `[longitude, latitude]`.

## Tasks

### 22.1 Placepix photo addresses shown as is

- **Status:** ✅ done (privacy text 2026-10-05T10:00Z names placepix.net as a fourth third-party request)
- **Goal:** An insight's `photo_key` and `photo_public_key` may hold `https://placepix.net/id/<n>/<w>/<h>` (it fits the 64-character column; no migration). `photo_service.public_url` returns such an address unchanged; `storage/base.check_key` still refuses it, and every path that would store, copy, probe, reconcile or delete a key (`photo_service.remove`, `remove_all`, publishing and withdrawing, `photo_reconcile`) leaves it alone. The host is one constant beside the key rules.
- **Depends on:** nothing.
- **Touches:** apps/api/src/{storage/base.py,services/photo_service.py,services/photo_reconcile.py}, their tests, docs/PRIVACY.md (the visitor's browser fetches these photos from placepix.net), the privacy text if it lists the hosts a page contacts.
- **Done when:** The tests above pass; a member's own photos behave exactly as before.
- **Reviews:** privacy review before merge (photo handling); tests in the same commit (decision 42's exception).

### 22.2 Generator: catalogue, members, places and the graph

- **Status:** ✅ done 2026-10-05; 69 tests, 100 % of the package; the real file is generated; photos were capped at three uses (task 23.4 changed the cap to seven and the photos to the photo library's)
- **Goal:** `tools/mockdata/` (uv, Python 3.12, Faker with the Arabic locales, typed, ruff), run by `make mock-data` (`MOCK_SEED`, `MOCK_MEMBERS=1000`):
  - **Catalogue.** `GET https://placepix.net/api/categories` and `/api/info/id/<n>`; keep animal, bird, cat, dog, flower, food, nature, city, travel, interior, education, transportation; drop `kid` and any filename naming a person, a face, a portrait of a human or a body, so no child or face is shown. A filename becomes the scene's labels and its Arabic line (a small reviewed word list, not a model).
  - **Members.** 22 countries (MA, DZ, TN, LY, EG, SD, MR, SA, AE, QA, KW, BH, OM, YE, JO, PS, SY, LB, IQ, SO, DJ, KM) weighted by the square root of their population with at least 10 each; cities from `geodata.geonames` (class P, population ≥ 15 000, `ar_name` set) weighted by population; Arabic display names, Latin handles, `<handle>@mock.tabsira.invalid`; sign-ups spread over the last six months; private profile fields left empty.
  - **Points.** Within 1.5 km of a real GeoNames place of the member's city (parks, landmarks, neighbourhoods: classes S, L, P), never at sea.
  - **Activity.** Lognormal: a few prolific members, many quiet ones. A placepix photo is used at most three times, never twice in one country, so the feed does not repeat itself. About 2000 insights, 1200 posts, 15 000 follows, 30 000 reactions, 4000 comment slots, 900 atlas entries; every count is a setting.
  - Writes the file of version 1 to `../tabsira-data/mock/`, deterministic for a seed.
- **Depends on:** nothing.
- **Touches:** tools/mockdata/ (new folder, approved by the owners on 2026-10-05), Makefile (`mock-data`), .gitignore if needed.
- **Done when:** Two runs with one seed give the same file byte for byte; its unit tests pass without the network (catalogue mocked) and against a small GeoNames fixture.

### 22.3 Importer and `--clean`

- **Status:** ✅ done (`make mock-import`, `make mock-clean`; the shape of `images[].insight` is the importer's `InsightBodyIn`, see its docstring)
- **Goal:** `python -m src.cli.import_mock <path-or-s3-url> --i-understand [--clean]` in `apps/api`, run by `make mock-import` and `make mock-clean`. It checks the file (version, the scripture guard over every text, every evidence id in the store), then writes members (verified, consent rows as at sign-up, `photo_storage_consent` on), scans and insights, completions, publications and posts, follows, reactions (on whatever table holds them when it runs: `post_likes` or the reactions of 21.3), comments, and atlas entries through the atlas service (approximate place, labels from GeoNames). Times are the file's. Idempotent by the `@mock.tabsira.invalid` addresses.
- **Depends on:** 22.1; the file's shape from 22.2.
- **Touches:** apps/api/src/cli/import_mock.py, tests/test_import_mock.py, Makefile, docs/OPERATIONS.md (how to import and clean on a host).
- **Done when:** The checks above pass at 100 % coverage of the new module.

### 22.4 Real processing of the photos

- **Status:** ✅ done 2026-10-05 on the retrieval of this branch, without the owners' rework (their call). OVHcloud for every stage (Qwen3.8-27B, bge-m3, reranker off), the detector on. 427 photos processed, stopped at 150 with an insight (147 needs a question, 73 no relevant evidence, 56 show someone, 1 sensitive, no error, no throttling, no fallback); 1000 members, 1050 insights, 1050 posts with 1049 reflections, 3954 of 4000 comments; 57 distinct verses and no hadith (no kept insight carries one); $4.99 in all ($3.95 photos, $1.04 texts); 1084 s recorded at 20 in parallel, plus about 30 min of an earlier run at four in parallel whose time was not recorded. The importer's checks passed, and the whole file imported into a throwaway database holding a copy of the store. Tests: 100 % of `tools/mockdata`.
- **Goal:** Run the real pipeline on each placepix photo (vision through the configured provider, OVHcloud for this run, then planner, retrieval, the evidence gate and the composer), as a member's scan, into a photo library the generator builds the activity from; then the posts' reflections and comments, through the scripture guard and the moderation like a member's.
  - `make mock-photos`: the kept catalogue in id order, 20 photos at once (halved on a 429 or a 5xx), until the library holds 150 photos with an insight; a photo whose outcome is not `insights`, whose scene is sensitive or that shows someone gives no insight. The library keeps every finished photo (outcome, provider, model, usage, cost, time, the insight) and is never redone unless `--reprocess`; nothing is written to the database.
  - `make mock-data`: photos from the library, up to seven uses each, another country when one is free, different months; the members, places and follows depend on the seed only.
  - `make mock-texts`: one call per post with the composer model (the small one, Qwen3.5-9B, wrote broken Arabic), from the insight's title, glimpse and small step only; each text through the social schemas' cleaning, `leaks` and the moderation of member text; kept in the texts library by post and photo; the importer's checks over the file before it is written; `process-report.json` beside it.
- **Depends on:** 22.2, 22.3.
- **Touches:** tools/mockdata/ (process, scan, voices, library, the generator), Makefile (`mock-photos`, `mock-texts`), docs/OPERATIONS.md.
- **Production `.env`:** no new key. The run reads the API's own settings on a development machine; `DB_POOL_SIZE` must be at least the number of photos at once.
- **Done when:** Every insight in the file was produced by the pipeline in that run; the run's cost and duration are written beside the file.
