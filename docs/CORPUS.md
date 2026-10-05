# The reference data archive

The scripture store, the world ontology and the learning path live in their own schema, `corpus`, and every installation gets them from one verified archive in the owners' bucket instead of rebuilding them from the third-party sources (decision 57). GeoNames comes from a dump in the same bucket; the scripture vectors from their own archive (docs/EMBEDDINGS.md).

The code: `scripts/corpus/` (export, import, ensure and the SQL they share), `scripts/geodata/ensure.sh`, the migration `apps/api/alembic/versions/20261004_209000_move_reference_data_to_corpus.py`.

## What is in `corpus`, and what is not

| In `corpus` (reference data, in the archive)                                                                                                | In `app` (written in production, never exported)                                                                                      |
| ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `quran_surahs`, `quran_verses`, `quran_verse_history`, `quran_verse_search`, the materialized view `quran_verse_spans`, `quran_annotations` | `hadith_rulings` (an editor's dorar.net rulings, decision 18), `hadith_verification_queue`, `scripture_audit`, `scripture_sync_state` |
| `hadith_collections`, `hadiths`, `hadith_search`, `hadith_signals`                                                                          | `ontology_candidates` (what the application learned, reviewed by a person)                                                            |
| `ontology_entities`, `learning_path_versions`, `learning_domains`, `learning_units`                                                         | every learner's state (`learner_unit_states`), completions, exposures, and everything else about a user                               |

The two schemas share one metadata and the app Alembic chain: the tables of `app` hold keys into `corpus` (a ruling names a hadith, a learner's state a unit), and the migrations that created the store already belong to that chain. A fourth chain would have to own tables the app chain created and run both before and after it; one revision that moves the tables (`ALTER TABLE … SET SCHEMA corpus`, instant, the keys follow) is simpler. The role's `search_path` is `app, corpus, geodata, vectors, public`, so unqualified SQL keeps working.

The daily Quran correction sync (decision 16) keeps writing `corpus.quran_verses` and `corpus.quran_verse_history` in place, and writes its audit entries and its state in `app`. The scripture write guard (`app.scripture_write_guard`) and the hash check on every verse and hadith moved with the tables.

## The archive

`tabsira-corpus-<date>.tar.gz` and its `.sha256`, in the owners' bucket under `tabsira/corpus/`. It holds:

- `corpus.dump`: `pg_dump -Fc --no-owner --no-privileges -n corpus`;
- `manifest.json`: the dump's SHA-256; per table its row count and a fingerprint (the SHA-256 of the SHA-256 of each row's text, in primary-key order, with the settings that make a row print the same on any server); for `quran_verses`, `quran_verse_history` and `hadiths` also a fingerprint of the stored text hashes alone; the Quran dump versions, the hadith datasets and the hashes of their files, the hash of the ontology workbook, the learning path versions with their source files and hashes, and the active version; the app revision and the PostgreSQL version it was made with;
- `state.sql` (the fingerprints), `verify.sql` (the checks), `force-guard.sql`, `import.sh`, `README.txt` and `SHA256SUMS` for all of them.

Nothing about any user is in it.

## Making one

On a machine whose database holds the whole store, migrated to the `corpus` schema:

```bash
DATABASE_URL=postgresql://tabsira:…@127.0.0.1:5432/tabsira scripts/corpus/export.sh   # → ../tabsira-data/corpus/
```

It refuses a store without the 6,236 verses, reads the state before and after the dump and stops if the data changed in between (the daily sync), then packs the archive and writes its `.sha256`. The owners upload both files; the default `CORPUS_ARCHIVE_URL` names the archive of 2026-10-04 and changes with each new one.

## Installing one

`make data` (and `deploy/load-data.sh`, and `scripts/data.ps1` on native Windows) runs `scripts/corpus/ensure.sh`:

1. Nothing to do when the corpus is there: 6,236 verses, hadiths, annotations, signals, the ontology and an active learning path. `--force` (or `DATA_FORCE=true`) installs again.
2. The archive comes from `CORPUS_ARCHIVE` (a local `.tar.gz` or extracted folder) or `CORPUS_ARCHIVE_URL`, downloaded once into `../tabsira-data/corpus` (`CORPUS_ARCHIVE_DIR`; `~/tabsira-data/corpus` in production) and checked against its `.sha256`.
3. `scripts/corpus/import.sh` checks every file against `SHA256SUMS` and the dump against the manifest; refuses a database whose corpus is not empty unless `--force`; with `--force` also refuses when rows outside `corpus` and `vectors` point at it (rulings, a learner's state, a reviewed candidate), because replacing the corpus would lose them. In one transaction it empties the corpus (with `--force`; the vectors of the old texts go with them and are imported again by the next step), restores the rows with `pg_restore --data-only`, checks every verse, past verse and hadith against `encode(sha256(convert_to(text, 'UTF8')), 'hex') = text_sha256` (the hash `src/scripture/text.py` computes), checks the count and the fingerprints of every table against the manifest, and rebuilds the verse spans. Any failed check rolls everything back. It ends by printing the counts and the active path version.

With `CORPUS_ARCHIVE_URL` set to empty (and no `CORPUS_ARCHIVE`), `make data` builds the store from its sources as before (quranpedia's dump, the nine hadith files, the two corpus files of `data/corpus/`) and imports the ontology and the learning path from the repository (`scripts/data-learning.sh`). A new learning path release in the repository therefore reaches an archive-installed server with the next archive, or by `scripts/data-learning.sh masar` run by hand.

### The Sunnah signals and decision 58

Since 5 October 2026 the signals import marks each match of a record with `cited` (the record's references cite that book); with the coverage of the record's best match, it decides whether a hadith that has no ruling yet may show (decision 58). An archive made before that carries no `cited` mark, so a host installed from it shows no hadith before its ruling: it fails closed, as decision 18 alone would. Two ways to bring the mark to a host:

- **A new archive, before the first editor ruling there.** On a machine that holds the corpus files, import the signals again (`uv run python -m src.cli.import_scripture signals --corpus-dir ../../data/corpus` from `apps/api`), make the archive (`scripts/corpus/export.sh`), publish it with its `.sha256`, set `CORPUS_ARCHIVE_URL` to it, and install it with `--force`. `--force` is refused once rulings point at the corpus (see step 3), so this way closes when the editors start.
- **The signals step alone, in place.** On the host, with `sunnah-enriched.json` in `CORPUS_DIR` (its SHA-256 is checked), the same `import_scripture signals` command replaces the signal rows and nothing else; rulings, learners' states and vectors are untouched. Re-importing the signals changes which unruled hadiths may show; an insight already kept follows the rule as it reads now.

## GeoNames

`scripts/geodata/ensure.sh`, called first by `make data` when `GEODATA_DUMP` or `GEODATA_DUMP_URL` is set (or `--geonames`), and by `deploy/load-data.sh` unless `--no-geonames`. Two sources, chosen with `--geonames-source=dump|geonames` or `GEONAMES_SOURCE`:

- `dump` (default): the verified snapshot of 2026-10-04, `tabsira/geodata/tabsira-geodata-2026-10-04.dump` and its `.sha256` (about 340 MB). Only the rows are restored, into the tables `make migrate` made, in one transaction that drops the plain indexes and builds them again after the load (`scripts/geodata/restore-{begin,end}.sql`); the geodata chain's `alembic_version` is kept.
- `geonames`: the original process, `scripts/seed-geonames.sh`, a fresh import from geonames.org: up-to-date data, but about 600 MB to download and about 15 minutes.

Either way it does nothing when `geodata.geonames` holds places, unless `--force`.
