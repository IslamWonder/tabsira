# Mock data generator

Writes `tabsira-mock-v1.json` for plan 22 (decision 63): about 1000 mock members in real cities
of 22 Arabic-speaking countries, with insights, posts, follows, reactions, comment slots and atlas
entries. The file holds references only (placepix ids, GeoNames ids, points, times). It never holds
a verse or a hadith, and `images[].insight`, reflections and comment texts stay `null` until task 22.4.

```bash
make mock-data                                  # MOCK_SEED=42 MOCK_MEMBERS=1000
MOCK_SEED=7 MOCK_MEMBERS=1500 make mock-data
uv run --project tools/mockdata python -m mockdata.cli --help
```

- Output, catalogue cache and places cache go to `../tabsira-data/mock/`, never committed.
- Same `--seed` and `--now` give the same bytes. Without `--now` the current UTC time is used.
- The placepix catalogue is fetched once (sequentially, with a small delay) and cached;
  `--refresh-catalogue` fetches again. Photos that name a person, a face or a body, and the `kid`
  category, are dropped.
- GeoNames is read from `geodata.geonames` of the development database, read only, with
  `DATABASE_URL` from the environment or `.env`; the selected cities and places are cached;
  `--refresh-places` reads again.
- Every volume is an option: `--insights`, `--posts`, `--follows`, `--reactions`, `--comments`,
  `--map-entries`. A photo is used at most three times and never twice in one country, so the
  number of insights is capped by the catalogue.
- Tests: `cd tools/mockdata && uv run pytest --cov`. No network, no database.
