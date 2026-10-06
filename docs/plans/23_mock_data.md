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
| Optional country in the profile                  | ✅     | task 23.7. Decision 67. Privacy review.    |

**How we check it**

- A placepix key is returned as is by the public photo address, and no storage call (put, copy, exists, delete, reconcile) ever receives one (tested).
- The file contains no verse or hadith text: the scripture guard runs over every text field before it is written, and the importer refuses a file that fails it (tested).
- Every evidence id of the file exists in the store; a missing one skips that insight and is reported, never replaced (tested).
- No public answer carries a mock member's exact point; their atlas entries go through `geo/privacy.py` like any other (tested).
- `import_mock` twice imports nothing the second time; `--clean` leaves no row owned by a `@mock.tabsira.me` account and touches no other (tested).
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
  - **Members.** 22 countries (MA, DZ, TN, LY, EG, SD, MR, SA, AE, QA, KW, BH, OM, YE, JO, PS, SY, LB, IQ, SO, DJ, KM) weighted by the square root of their population with at least 10 each; cities from `geodata.geonames` (class P, population ≥ 15 000, `ar_name` set) weighted by population; Arabic display names, Latin handles, `<handle>@mock.tabsira.me`; sign-ups spread over the last six months; private profile fields left empty.
  - **Points.** Within 1.5 km of a real GeoNames place of the member's city (parks, landmarks, neighbourhoods: classes S, L, P), never at sea.
  - **Activity.** Lognormal: a few prolific members, many quiet ones. A placepix photo is used at most three times, never twice in one country, so the feed does not repeat itself. About 2000 insights, 1200 posts, 15 000 follows, 30 000 reactions, 4000 comment slots, 900 atlas entries; every count is a setting.
  - Writes the file of version 1 to `../tabsira-data/mock/`, deterministic for a seed.
- **Depends on:** nothing.
- **Touches:** tools/mockdata/ (new folder, approved by the owners on 2026-10-05), Makefile (`mock-data`), .gitignore if needed.
- **Done when:** Two runs with one seed give the same file byte for byte; its unit tests pass without the network (catalogue mocked) and against a small GeoNames fixture.

### 22.3 Importer and `--clean`

- **Status:** ✅ done (`make mock-import`, `make mock-clean`; the shape of `images[].insight` is the importer's `InsightBodyIn`, see its docstring)
- **Goal:** `python -m src.cli.import_mock <path-or-s3-url> --i-understand [--clean]` in `apps/api`, run by `make mock-import` and `make mock-clean`. It checks the file (version, the scripture guard over every text, every evidence id in the store), then writes members (verified, consent rows as at sign-up, `photo_storage_consent` on), scans and insights, completions, publications and posts, follows, reactions (on whatever table holds them when it runs: `post_likes` or the reactions of 21.3), comments, and atlas entries through the atlas service (approximate place, labels from GeoNames). Times are the file's. Idempotent by the `@mock.tabsira.me` addresses.
- **Depends on:** 22.1; the file's shape from 22.2.
- **Touches:** apps/api/src/cli/import_mock.py, tests/test_import_mock.py, Makefile, docs/OPERATIONS.md (how to import and clean on a host).
- **Done when:** The checks above pass at 100 % coverage of the new module.

### 22.4 Real processing of the photos

- **Status:** ✅ done 2026-10-05 on the retrieval of this branch, without the owners' rework (their call). OVHcloud for every stage (Qwen3.8-27B, bge-m3, reranker off), the detector on. 427 photos processed, stopped at 150 with an insight (147 needs a question, 73 no relevant evidence, 56 show someone, 1 sensitive, no error, no throttling, no fallback); 1000 members, 1050 insights, 1050 posts with 1049 reflections, 3954 of 4000 comments; 57 distinct verses and no hadith (no kept insight carries one); $4.99 in all ($3.95 photos, $1.04 texts); 1084 s recorded at 20 in parallel, plus about 30 min of an earlier run at four in parallel whose time was not recorded. The importer's checks passed, and the whole file imported into a throwaway database holding a copy of the store. Tests: 100 % of `tools/mockdata`.
- **Hadith pass:** the run above used the evidence rule of decision 58, under which a hadith with no ruling shows only when the enriched Sunnah file links it as `cited`; the development store's 3920 signals carry no `cited` mark and no ruling is recorded, so every hadith the gate wanted was held back. Decision 65 shows them; `--add-hadith` runs the 150 kept photos again under it (see the README). Run on 2026-10-05 at 20 in parallel on OVHcloud, detector on: 46 photos took a new insight with a hadith (36 distinct, every one in the store with its hash; 9 of them without a verse), 104 kept their insight (49 now ask a question, 30 find no relevant evidence, 19 no hadith, 6 show someone); one 5xx halved the parallel calls; 537 s, $2.26 added. Kept insights: 150, 46 with a hadith, 141 with a verse, 64 distinct verses. The file and the texts of those 46 photos' posts are to be regenerated (`make mock-data`, `make mock-texts`).
- **Goal:** Run the real pipeline on each placepix photo (vision through the configured provider, OVHcloud for this run, then planner, retrieval, the evidence gate and the composer), as a member's scan, into a photo library the generator builds the activity from; then the posts' reflections and comments, through the scripture guard and the moderation like a member's.
  - `make mock-photos`: the kept catalogue in id order, 20 photos at once (halved on a 429 or a 5xx), until the library holds 150 photos with an insight; a photo whose outcome is not `insights`, whose scene is sensitive or that shows someone gives no insight. The library keeps every finished photo (outcome, provider, model, usage, cost, time, the insight) and is never redone unless `--reprocess`; nothing is written to the database.
  - `make mock-data`: photos from the library, up to seven uses each, another country when one is free, different months; the members, places and follows depend on the seed only.
  - `make mock-texts`: one call per post with the composer model (the small one, Qwen3.5-9B, wrote broken Arabic), from the insight's title, glimpse and small step only; each text through the social schemas' cleaning, `leaks` and the moderation of member text; kept in the texts library by post and photo; the importer's checks over the file before it is written; `process-report.json` beside it.
- **Depends on:** 22.2, 22.3.
- **Touches:** tools/mockdata/ (process, scan, voices, library, the generator), Makefile (`mock-photos`, `mock-texts`), docs/OPERATIONS.md.
- **Production `.env`:** no new key. The run reads the API's own settings on a development machine; `DB_POOL_SIZE` must be at least the number of photos at once.
- **Done when:** Every insight in the file was produced by the pipeline in that run; the run's cost and duration are written beside the file.

### 23.5 Every feature, complete accounts, privacy fixes

- **Status:** ✅ done 2026-10-05 ; the library holds 187 photos with an insight (132 with a hadith), the file 1020 insights (707 with a verse and a hadith, 71 distinct verses, 87 distinct hadiths), imported end to end into a throwaway database
- **Goal:** The mock members look and work like members who signed up and used everything, so the judges meet no surprise.
  - **Accounts.** The domain is `mock.tabsira.me` (the sign-in schema refuses `.invalid`); the mailer refuses it in `email_service.deliver`. Every member is active, verified, has accepted the terms and the privacy text at the current versions, has the tutorial closed (they hold their own insights), a completed profile (every answer, the photo consent, a public name, a third with the full-name consent) and signs in with the password `tabsira`, hashed by the app's function with the configured rounds (**an owners' decision for the contest's judges: production is reset at launch**). Names are drawn from reviewed lists by the declared gender (Faker's Arabic providers gave tribes and invented first names); handles read like them.
  - **Features.** Posts for everyone and for followers only, with and without photo and reflection; both reactions; bookmarks; follows; a few blocks that touch no popular author and no pair that interacted; comments and replies; atlas entries, about a tenth orphaned by `orphan_service.mark_one` (generalisation rows as the job writes them), half of those sponsored with a sponsor note written by the texts stage (cached in `texts-library.json`, guards and moderation as for a comment); completions through `completion_service.remember` and `place_in_world` (the same functions the first «تمّ» calls) at the file's times, with streaks for the prolific; reviewed insight ratings. No report and no moderation action by a person. The services run with every feature on, whatever the host's switches.
  - **Privacy fixes (review).** `--clean` counts other members' rows that hang on mock accounts (comments, replies, reactions, bookmarks, follows, blocks, sponsorships, reports), prints them and refuses without `--also-dependent-rows`; the template database is refused like a test one; the placepix id is bounded and the stored address asserted; it never calls the storage; the scripture guard covers members' names and handles; reflections, comments and sponsor notes pass the app's text checks (cleaning, scripture look-alike, no link, address or number); an S3 file over 64 MB is refused by its length; public photos load with `referrerPolicy="no-referrer"`; the privacy text gives placepix its own section and basis (version 2026-10-05T23:00Z) and `docs/PRIVACY.md` no longer calls OpenFreeMap the one third-party request.
- **Depends on:** 23.3, 23.4; main's decisions 60, 61, 64.
- **Touches:** apps/api/src/{cli/import_mock.py,mock_accounts.py,services/email_service.py,services/completion_service.py}, tools/mockdata, apps/web (public photo, legal text), docs.
- **Production `.env`:** no new key. The privacy text version moved to 2026-10-05T23:00Z (`PRIVACY_VERSION`, already in both examples).
- **Done when:** 100 % of `import_mock.py` and of `tools/mockdata`; a mock member signs in with `tabsira` through the API and reads feed, profile, world and an atlas entry.

### 23.7 Optional country in the profile, public by its own switch

- **Status:** ✅ done 2026-10-05
- **Goal:** decision 67. A member may declare a country and, separately, choose to show it; the mock members get the country of the file, about seven in ten shown.
- **Done:** `profiles.country` (ISO2, nullable, shape checked by the database, existence checked against GeoNames by `profile_service`, 422 for an unknown code) and `profiles.show_country` (mirror of the new `public_country` consent kind, off by default), migration `20261005_200000` on the app chain. `PATCH /profile` takes `country` (null clears it), `POST /consents` takes `public_country`; under 13 it is refused, declaring under 13 withdraws it, and `public_identity.shown_countries` never returns the country of such an account. `GET /u/{handle}` (`MemberProfileOut.country`) and every post's author (`PostAuthorOut.country`, feeds, member posts, a post) carry `{code, name}` only while the switch is on; `MemberOut` (comments, blocks, the atlas) and public insights do not. The Arabic name is the label `GET /geo/countries` gives, read once per process (`geo_service.country_labels`). `ProfileOut` carries both fields, so `GET /account/export` does; the profile row goes with the account. Web: a country select (native, type-ahead, sorted by the Arabic name, «لا أريد التحديد» first) and the switch under it in «ملفي», the country after the handle on a post («· تونس») and after the month joined on a public profile; consent text version `2026-10-05.2`. `import_mock` declares `members[].country` and answers the switch from a SHA-256 of the handle (70 %), once, completing members imported earlier; an unknown code is reported and left empty. Privacy text `2026-10-05T23:30Z` (terms unchanged).
- **Touches:** apps/api/src/{models/profile.py,models/consent.py,schemas/profile.py,schemas/social.py,schemas/geo.py,services/profile_service.py,services/public_identity.py,services/geo_service.py,services/member_service.py,services/post_view.py,cli/import_mock.py}, apps/api/alembic/versions/20261005_200000_add_profile_country.py, apps/web/src/{account,components/me/settings-section.tsx,components/community,messages,lib/api}, docs.
- **Tests:** `tests/test_profile_country.py` (the country is absent from every public answer while the switch is off, and only in the profile and the post author while on), `tests/test_import_mock.py` (100 % of `import_mock.py`), Vitest for the settings, the post card, the profile screen and the country list.
- **Production `.env`:** no new key. `PRIVACY_VERSION` moves to `2026-10-05T23:30Z` in `.env.example` and `deploy/env.production.example`; the owners set the same value in production, and every account accepts the privacy text again at its next visit.
- **Reviews:** privacy review before merge (profile, consent, public identity); its findings on the under-13 guard and the tests are fixed.

### 23.8 Views of the mock posts

- **Status:** ✅ done 2026-10-06 00:45 (Tunis)
- **Goal:** task 16.3 counts the views of a post; the mock posts get a plausible count instead of zero.
- **Done:** every post of the file carries `views`, from its own seeded stream (`<seed>:views`), so the rest of the file stays byte for byte the same and the texts library is reused as is: at least every member who reacted, saved or commented, eight readers for each of them plus a long tail (median about 20), and a followers-only post keeps three tenths of that reach. `import_mock` writes it into `posts.views_count`; a file without it gives zero.
- **Touches:** tools/mockdata/src/mockdata/{activity,output}.py and their tests, apps/api/src/cli/import_mock.py and `tests/test_import_mock.py`.
- **Production `.env`:** no new key.
- **To apply:** a new file gets the views from the generator; on mock posts already imported, the `views` fill-in of task 23.9.

### 23.9 Fill-ins for mock data already imported

- **Status:** ✅ done 2026-10-06 (Tunis)
- **Goal:** a feature added after the mock import shows on the mock rows already there, without a `--clean` that renumbers every post and drops what real members left on them.
- **Done:** `import_mock --fill-in <name>` (repeatable, one transaction, `--i-understand` and `--allow-production` as for the import) runs named fill-ins from `apps/api/src/cli/mock_fill_ins.py` (`FILL_INS`); `scripts/mock-data.sh fill-in <name>...` backs up the app schema first, and `make mock-fill-in MOCK_FILL_IN=<name>` calls the importer directly. The first fill-in, `views`, gives every published mock post the generator's kind of view count, seeded by the post's id, never lower than what it has. A rule in `AGENTS.md` and a section of `tools/mockdata/README.md`: every feature the mock data should show comes with its generator change, its import and its fill-in.
- **Touches:** apps/api/src/cli/{import_mock,mock_fill_ins}.py, apps/api/tests/test_mock_fill_ins.py, scripts/mock-data.sh, Makefile, tools/mockdata/README.md, tools/mockdata/src/mockdata/activity.py (a comment), docs/OPERATIONS.md, AGENTS.md.
- **Production `.env`:** no new key.
- **To apply:** after deploying, `scripts/mock-data.sh fill-in views --allow-production` on production and `scripts/mock-data.sh fill-in views` on a development machine.

### 23.10 Patch some photos' insights in the mock file

- **Status:** 🟡 generator side done 2026-10-06 (tests 100 % of `tools/mockdata`); the in-place rewrite of imported insights in `apps/api` is another change and not done here
- **Goal:** a scripture audit found about 39 photos whose insight is wrong. They run through the pipeline again and the result goes into the file without regenerating it, so which members use which photo, the refs and the posts already imported stay as they are.
- **Done:** `python -m mockdata.process photos --only <ids>` (exactly those photos, again, ids checked against the catalogue, usage added to the photo's); `python -m mockdata.process patch --photos <ids>` (`make mock-patch MOCK_PHOTOS=<ids>`) replaces `images[].insight` and the scene of those photos only from the library, `null` when the outcome is no longer `insights`, runs the importer's checks, writes atomically and records `patch-report.json` (from which verse and hadith to which, which became null). `make mock-texts` then writes again the posts' and sponsor notes' texts of the patched photos only (the library's `insight_at` mechanism of `--add-hadith`; the patch marks the changed photos again so a texts run before it does not defeat it).
- **Touches:** tools/mockdata/src/mockdata/{patch,process}.py, tools/mockdata/tests/{test_patch,test_process}.py, tools/mockdata/README.md, Makefile (`mock-patch`).
- **Production `.env`:** no new key.
- **To apply:** on the machine holding `../tabsira-data/mock/` and the provider keys: `MOCK_ARGS="--only <ids>" make mock-photos`, `make mock-patch MOCK_PHOTOS=<ids>`, `make mock-texts`, upload the file to the bucket; then the importer's in-place rewrite on production (apps/api, not part of this task's code).
