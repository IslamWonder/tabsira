# Setting up a machine

A new laptop (Linux, macOS, or Linux in a virtual machine on Windows) ready to work: the databases filled with the reference data (the `corpus` schema: scripture store, world ontology, learning path; docs/CORPUS.md), GeoNames and the scripture vectors, and the app running at `http://tabsira.test`, **without importing anything that is already there**. Every step below is safe to run again, and each one starts with the check that tells you it is already done. Task 15.4 turns these steps into one command, `make bootstrap`. Windows itself, without a virtual machine: [docs/SETUP-WINDOWS.md](SETUP-WINDOWS.md); there `scripts/data.ps1` does what `make data` does (below).

Artifacts you make while working (exports, reports) go beside the checkout in `../tabsira-artifact/`, never into the repository.

## What you need from the owners

| What                                                | Where                                                                                                                                                         | Needed for                                   |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| The repository                                      | GitHub or Gitea                                                                                                                                               | everything                                   |
| The reference data archive                          | public: `https://s3-v2.riastorage.com/tabsira/corpus/tabsira-corpus-2026-10-04.tar.gz` and its `.sha256` (docs/CORPUS.md); `make data` downloads it           | the scripture store, ontology, learning path |
| The GeoNames dump                                   | public: `https://s3-v2.riastorage.com/tabsira/geodata/tabsira-geodata-2026-10-04.dump` and its `.sha256`                                                      | place search, the atlas                      |
| The scripture vectors                               | public: `https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz` and its `.sha256` (docs/EMBEDDINGS.md)                               | the insight engine's search                  |
| The two project corpora (only to rebuild the store) | the owners' bucket, `tabsira/corpus/`: `quran-annotations.json`, `sunnah-enriched.json`, `SHA256SUMS` (docs/ASSET_MANIFEST.md gives their source and SHA-256) | `make data` with `CORPUS_ARCHIVE_URL` empty  |
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

`make migrate` (geodata chain, then app, which also fills the `corpus` schema, then vectors: decisions 48 and 57). Always safe: it applies only what is missing.

### 4. Reference data, GeoNames, vectors: `make data`

`make data` (`scripts/data.sh`) installs, in this order and each once only: GeoNames, the corpus, the vectors. Every step checks first and skips what is there; nothing already in your database is imported again. `DATA_FORCE=true make data` (or `bash scripts/data.sh --force`) installs everything again. On native Windows: `powershell -ExecutionPolicy Bypass -File scripts\data.ps1` with `-Force`, `-Geonames`, `-NoGeonames`, `-GeonamesSource dump|geonames` (run on Windows on 5 October 2026 for the corpus and the vectors, with `-Force` over a partly filled corpus; its GeoNames dump path is not yet run there. It has no `geonames` source and does not rebuild the store from its sources: use WSL for those). `scriptswindowsoad-data.ps1` runs it and then checks the four schemas, as `deploy/load-data.sh` does in production.

What is there:

```sql
SELECT (SELECT count(*) FROM corpus.quran_verses)                    AS verses,       -- 6236
       (SELECT count(*) FROM corpus.hadiths)                         AS hadiths,      -- 65712
       (SELECT count(*) FROM corpus.ontology_entities)               AS ontology,     -- 1000
       (SELECT path_version FROM corpus.learning_path_versions WHERE is_active) AS path,
       (SELECT count(*) FROM geodata.geonames)                       AS places,       -- millions
       (SELECT count(*) FROM vectors.quran_verse_embeddings)         AS verse_vectors,   -- 18708
       (SELECT count(*) FROM vectors.hadith_embeddings)              AS hadith_vectors;  -- 146364
```

#### GeoNames

On a development machine `make data` installs GeoNames only when you ask: set `GEODATA_DUMP_URL` (the dump's address above) or `GEODATA_DUMP` (a local copy) in `.env`, or run `bash scripts/data.sh --geonames`. Two sources, `--geonames-source=dump|geonames` or `GEONAMES_SOURCE` in `.env`:

- `dump` (default): the verified snapshot of 2026-10-04 from the bucket, downloaded once into `../tabsira-data/geodata/` (about 340 MB) and checked against its `.sha256`; only its rows are restored, into the tables `make migrate` made.
- `geonames`: the original import, `scripts/seed-geonames.sh`, with fresh data from geonames.org; it downloads about 600 MB (cached in `data/cache/geonames`) and takes about 15 minutes. `bash scripts/seed-geonames.sh --limit 50000` gives a small, quick set.

Both skip a filled `geodata.geonames` unless `--force`.

#### The corpus

`scripts/corpus/ensure.sh` downloads the archive named by `CORPUS_ARCHIVE_URL` once into `../tabsira-data/corpus/` (about 50 MB, verified against its `.sha256`), or takes `CORPUS_ARCHIVE` (a local `.tar.gz` or its extracted folder), and imports it with every verse and hadith checked against its stored hash and every table against the manifest (docs/CORPUS.md). With `CORPUS_ARCHIVE_URL=` empty it builds the store from its sources instead (quranpedia's dump and the nine hadith files, cached in `data/cache/`, plus the two project corpora: download them from `tabsira/corpus/` into `data/corpus/` and check them with `cd data/corpus && sha256sum -c SHA256SUMS`), then the ontology and the learning path from the repository.

#### The vectors

`scripts/vectors/ensure.sh` downloads the archive named by `VECTORS_ARCHIVE_URL` into `../tabsira-data/vectors/` once (930 MB, verified against its `.sha256`), extracts it and runs `scripts/vectors/import.sh`; a copy you already have is used instead when `VECTORS_ARCHIVE` points at the `.tar.gz` or its extracted folder. Only then does `embed_corpus` run, and finds nothing to compute. Never run `embed_corpus` with an API key before this step: it would pay for vectors the archive holds (docs/EMBEDDINGS.md).

### 5. Run

`make dev` starts the API, the web app, the vision service and the scan worker; open `http://tabsira.test`. `make smoke` checks the main pages and routes. `make stats` prints a short summary of the code.

## Importing again

Every import runs once: each step of `make data` skips what is there. To install again anyway: `bash scripts/data.sh --force` (or `DATA_FORCE=true make data`); one step alone: `bash scripts/corpus/ensure.sh --force`, `bash scripts/geodata/ensure.sh --force [--geonames-source=geonames]`, `bash scripts/vectors/ensure.sh --force`. Replacing the corpus is refused while editor rulings or learners' states point at it (docs/CORPUS.md).
