# 22 · Mock members to start the platform

**Phase:** 2 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-05 (Tunis)

The platform opens with about 1000 mock members living in real cities of the Arabic-speaking Muslim-majority countries, each with insights, posts, reactions, follows, comments and atlas entries, so the feed, the atlas and the camera discovery are alive on the first day (decision 63). Their photos are placepix.net's; their insights come from the real pipeline. Nothing on screen marks them as mock.

Two programs and one file:

1. **The generator** (`tools/mockdata/`, its own uv project) reads the placepix catalogue and the GeoNames tables and writes `tabsira-mock-v<N>.json` to `../tabsira-data/mock/`. The file is never committed; the owners upload it to their bucket (s3-v2) and regenerate it when retrieval changes.
2. **The importer** (`python -m src.cli.import_mock`, in `apps/api`) reads that file from a path or the bucket and writes the rows through the application's own services, so approximate places, public ids and photo rules are the ones members get. `--clean` removes every mock row.
3. **The file** holds references only: placepix ids, GeoNames ids, exact points, times, evidence ids (surah and ayah, collection and number) and the composed insight text. Never a verse or a hadith text.

| Step                                             | Status | Notes                                                    |
| ------------------------------------------------ | ------ | -------------------------------------------------------- |
| Placepix photo addresses shown as is             | ✅     | Task 22.1. Decision 63. Privacy review.                  |
| Generator: catalogue, members, places, the graph | ⬜     | Task 22.2.                                               |
| Importer and `--clean`                           | ✅     | Task 22.3.                                               |
| Real processing of every photo                   | ⏸      | Task 22.4, after the owners' retrieval rework is pulled. |

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

`images[].insight` is `null` until task 22.4 fills it with the pipeline's outcome (evidence ids, the reasons they were chosen, the composed text, the concept). Reflections and comment texts are `null` until then too; the importer skips what is still empty. Points are GeoJSON order, `[longitude, latitude]`.

## Tasks

### 22.1 Placepix photo addresses shown as is

- **Status:** ✅ done (privacy text 2026-10-05T10:00Z names placepix.net as a fourth third-party request)
- **Goal:** An insight's `photo_key` and `photo_public_key` may hold `https://placepix.net/id/<n>/<w>/<h>` (it fits the 64-character column; no migration). `photo_service.public_url` returns such an address unchanged; `storage/base.check_key` still refuses it, and every path that would store, copy, probe, reconcile or delete a key (`photo_service.remove`, `remove_all`, publishing and withdrawing, `photo_reconcile`) leaves it alone. The host is one constant beside the key rules.
- **Depends on:** nothing.
- **Touches:** apps/api/src/{storage/base.py,services/photo_service.py,services/photo_reconcile.py}, their tests, docs/PRIVACY.md (the visitor's browser fetches these photos from placepix.net), the privacy text if it lists the hosts a page contacts.
- **Done when:** The tests above pass; a member's own photos behave exactly as before.
- **Reviews:** privacy review before merge (photo handling); tests in the same commit (decision 42's exception).

### 22.2 Generator: catalogue, members, places and the graph

- **Status:** ⬜ open
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

### 22.4 Real processing of every photo

- **Status:** ⏸ waiting on the owners' retrieval rework
- **Goal:** For each kept placepix photo, run the real pipeline on the image itself (vision through the configured provider, OVHcloud by default for this run, then planner, retrieval, the evidence gate and the composer) and store its outcome in `images[].insight`: outcome, evidence ids and why, the composed text, the concept. A photo whose outcome is not `insights` is dropped. Reflections and comments are written by the composer's model from the post's own insight, then pass the scripture guard and moderation like a member's; one that fails is dropped.
- **Depends on:** the owners' new retrieval logic on `main`, 22.2.
- **Touches:** tools/mockdata/ (the processing step, calling `apps/api` as a library).
- **Done when:** Every insight in the file was produced by the pipeline in that run; the run's cost and duration are written beside the file.
