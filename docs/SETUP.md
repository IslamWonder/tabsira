# Setting up a machine

A new laptop (Linux, macOS, or Linux in a virtual machine on Windows) ready to work: the databases filled with the scripture store, GeoNames and the scripture vectors, and the app running at `http://tabsira.test`, **without importing anything that is already there**. Every step below is safe to run again, and each one starts with the check that tells you it is already done. Task 15.4 turns these steps into one command, `make bootstrap`.

Artifacts you make while working (exports, reports) go beside the checkout in `../tabsira-artifact/`, never into the repository.

## What you need from the owners

| What                                                | Where                                                                                                                                                         | Needed for                                   |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| The repository                                      | GitHub or Gitea                                                                                                                                               | everything                                   |
| The two project corpora (too large for git, 150 MB) | the owners' bucket, `tabsira/corpus/`: `quran-annotations.json`, `sunnah-enriched.json`, `SHA256SUMS` (docs/ASSET_MANIFEST.md gives their source and SHA-256) | `make data` (search annotations and signals) |
| The GeoNames export (optional, saves the import)    | the owners' bucket, `tabsira/geodata/`: `tabsira-geodata-2026-10-04.dump` and its `.sha256`                                                                   | place search, the atlas                      |
| The scripture vectors                               | public: `https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz` and its `.sha256` (docs/EMBEDDINGS.md)                               | the insight engine's search                  |
| An OpenAI key (optional)                            | `AI_OPENAI__API_KEY` in your `.env`                                                                                                                           | real scans; without it the demo engine runs  |

## Steps

### 1. System, database server, local nginx

Done when `psql "$(grep ^SYNC_DATABASE_URL= .env | cut -d= -f2- | sed 's/+psycopg//')" -c 'select 1'` answers and `http://tabsira.test` resolves.

- Install Node 24, pnpm and uv yourself (nvm, fnm, brew: your choice).
- Ubuntu or Mint: `sudo bash scripts/provision-dev.sh` installs PostgreSQL 18 with PostGIS, pgvector and TimescaleDB, the quality tools, creates the role, the databases and `.env` (`scripts/setup-db.sh`), and sets up nginx for `tabsira.test` on port 80, plain HTTP (decision 49). Idempotent.
- macOS: `bash scripts/install-postgres.sh`, then `bash scripts/setup-db.sh` and `bash scripts/setup-nginx-local.sh` (the provisioning script is for Ubuntu).
- Redis must run on 127.0.0.1:6379 (scans use it).

### 2. Dependencies and git hooks

`make install`. Done when it finishes without error; it is quick when nothing changed.

### 3. Database schemas

`make migrate` (geodata chain, then app, then vectors: decision 48). Always safe: it applies only what is missing.

### 4. The two corpora

Done when `cd data/corpus && sha256sum -c SHA256SUMS` says OK for both files. Otherwise download the three files from `tabsira/corpus/` into `data/corpus/` and run the check.

### 5. Scripture store, world ontology, learning path

Check first:

```sql
SELECT (SELECT count(*) FROM app.quran_verses)  AS verses,   -- 6236 when imported
       (SELECT count(*) FROM app.hadiths)        AS hadiths;  -- 65712 when imported
```

If both are full, `make data` sees it and skips the store (its guard: the whole Quran, hadiths, annotations and signals present). Otherwise `make data`. It is idempotent (downloads are cached in `data/cache/` and checked against their SHA-256, rows are matched by their hash), so running it again only costs a few minutes. `make data` imports the vectors from the published archive before it runs `embed_corpus` (step 7), so nothing is computed.

### 6. GeoNames

Check first: `SELECT count(*) FROM geodata.geonames;` — millions of rows when imported (a `--limit` import holds fewer). If it has rows, skip.

Otherwise, fastest: restore the export.

```bash
sha256sum -c tabsira-geodata-2026-10-04.dump.sha256
pg_restore --no-owner --role=tabsira --clean --if-exists --schema=geodata -d "<your database URL>" tabsira-geodata-2026-10-04.dump
```

Or import from GeoNames itself: `bash scripts/seed-geonames.sh` (it refuses to run on a filled `geodata.geonames` unless `--force` is given) (downloads about 600 MB from geonames.org into `data/cache/geonames`, reused afterwards, and imports several million rows; `--limit 50000` for a small, quick set). Note that `seed-geonames.sh` replaces the tables on every run: run it only when the check says the data is missing.

### 7. Scripture vectors

Check first:

```sql
SELECT (SELECT count(*) FROM vectors.quran_verse_embeddings) AS verse_vectors,   -- 18708
       (SELECT count(*) FROM vectors.hadith_embeddings)      AS hadith_vectors;  -- 146364
```

If both are full, `make data` skips it (its guard). Otherwise `make data` does it: its vectors step (`scripts/vectors/ensure.sh`) makes the same check, downloads the archive named by `VECTORS_ARCHIVE_URL` into `../tabsira-data/vectors/` once (930 MB, verified against its `.sha256`), extracts it and runs `scripts/vectors/import.sh`; a copy you already have is used instead when `VECTORS_ARCHIVE` points at the `.tar.gz` or its extracted folder. Only then does `embed_corpus` run, and finds nothing to compute. Never run `embed_corpus` with an API key before this step: it would pay for vectors the archive holds (docs/EMBEDDINGS.md).

### 8. Run

`make dev` starts the API, the web app, the vision service and the scan worker; open `http://tabsira.test`. `make smoke` checks the main pages and routes. `make stats` prints a short summary of the code.

## Importing again

Every import is meant to run once: `make data` skips the scripture store and the vectors when they are there, and `scripts/seed-geonames.sh` refuses a filled GeoNames table. To import again anyway: `bash scripts/data.sh --force` (or `DATA_FORCE=true make data`) and `bash scripts/seed-geonames.sh --force`.

## Everything at once

One query that says what is already there (run it with `psql` against your development database):

```sql
SELECT (SELECT count(*) FROM app.quran_verses)                    AS verses,
       (SELECT count(*) FROM app.hadiths)                         AS hadiths,
       (SELECT count(*) FROM geodata.geonames)                    AS places,
       (SELECT count(*) FROM app.ontology_entities)               AS ontology_entities,
       (SELECT count(*) FROM app.learning_path_versions)          AS learning_path_versions,
       to_regclass('vectors.hadith_embeddings') IS NOT NULL       AS vectors_schema;
```
