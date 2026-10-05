# Mock data generator

Writes `tabsira-mock-v1.json` for plan 23 (decision 66): about 1000 mock members in real cities
of 22 Arabic-speaking countries, with insights, posts, follows, reactions, comments and atlas
entries. The file holds references and the pipeline's composed words only (placepix ids,
GeoNames ids, points, times, evidence ids). It never holds a verse or a hadith.

Three steps, in this order:

```bash
make mock-photos     # the real pipeline over the placepix photos -> photo-library.json
make mock-data       # members, places and activity from the library's photos -> the file
make mock-texts      # the posts' reflections and comments -> texts-library.json and the file
```

`MOCK_SEED=7 MOCK_MEMBERS=1500 make mock-data`, `MOCK_ARGS="--limit 5" make mock-photos` and
`uv run --project tools/mockdata python -m mockdata.cli --help` give the options.

## The generator

- Output, catalogue cache, places cache and the two libraries live in `../tabsira-data/mock/`,
  never committed.
- Same `--seed`, `--now` and photo library give the same bytes. Without `--now` the current UTC
  time is used. The members, their cities and the follows depend on the seed alone, so they stay
  the same when the photo library grows.
- The photos are the photo library's that gave an insight (`--photos-from`, default
  `photo-library.json`), each carried with its insight. A photo is used up to seven times, in a
  country it has not been seen in when one is free, and its uses fall in different months when
  the member's months allow it.
- GeoNames is read from `geodata.geonames` of the development database, read only, with
  `DATABASE_URL` from the environment or `.env`; the selected cities and places are cached;
  `--refresh-places` reads again.
- Every volume is an option: `--insights`, `--posts`, `--follows`, `--reactions`, `--comments`,
  `--map-entries`. The number of insights is capped by the photos (seven uses each).
- Tests: `cd tools/mockdata && uv run pytest --cov`. No network, no database.

## The photo and text stages (task 23.4)

`python -m mockdata.process photos` and `python -m mockdata.process texts` run the real scan
pipeline of `apps/api` and the members' words:

- `apps/api` is used as a library: its dependencies come with this project (a virtual path
  dependency, `[tool.uv.sources]`) and `PYTHONPATH` puts its `src` on the path. The settings are
  the API's own (`.env` at the root, or `TABSIRA_ENV_FILE`); `AI_PROVIDER` chooses the provider.
  Many photos at once need a larger `DB_POOL_SIZE` (each running photo holds one connection).
- The photo stage takes the kept placepix catalogue (`placepix-catalogue.json`, fetched once) in
  id order and runs every photo the library does not hold through the image check, the detector
  (`DETECTOR_URL`; skipped when it does not answer), the scene analysis and moderation, the
  scripture guard, the insight engine and the server's acceptance, as a member's scan does for a
  new member. Nothing is written to the database: each photo's run is one transaction rolled
  back at the end.
- A photo counts as an insight only when the outcome is `insights`, the scene is not sensitive
  and nothing in the scene or the insight's clues speaks of a person. The library keeps every
  finished photo with its outcome (`insights`, `needs_clarification`, `no_relevant_evidence`,
  `people`, `sensitive`, `error`), provider, model, cost and time, and the first accepted insight
  in the importer's shape (`InsightBodyIn`). A photo that failed in a way another run may fix
  (a provider or the database did not answer, the download failed) is left out and tried again
  next time. A photo the library holds is never run again unless `--reprocess`.
- It stops as soon as the library holds `--stop-at` photos with an insight (150; `0` for all);
  the photos not reached stay unprocessed. `--parallel` photos run at once (20) and as many
  model calls; a 429 or a 5xx halves that for the rest of the run, and eight photos failed in a
  row send the rest to `--fallback` (OpenAI). Each run is recorded in the library.
- The texts stage makes one call per post with the provider's composer model, from the
  insight's title, glimpse and small step only. Each text passes the social schemas' cleaning,
  the scripture guard with the store and the moderation of member text; one that fails is
  dropped, and a reply to a dropped comment with it. Accepted texts are kept in
  `texts-library.json` by post and photo, and reused while the post's comment slots are the same.
- Before the file is replaced, the importer's checks run over it (shape, scripture guard, every
  evidence id in the store); `process-report.json` says what was kept and dropped and why, the
  models, the time, the tokens and the cost of both stages.
