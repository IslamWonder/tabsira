# Scripture embeddings

The vectors the insight engine searches with (decision 41 for reranking, `docs/BENCHMARK.md` for the measurements). They are computed once, exported to one archive, and imported by every installation, so nobody pays to compute them again.

The code lands with task 05.1 (branch `task/05.1-insight-engine` until it merges): `apps/api/src/retrieval/` (documents, embedding store), `apps/api/src/cli/embed_corpus.py`, `apps/api/src/models/retrieval.py`.

## What is embedded

One **retrieval document** per Quran verse and per hadith (`src/retrieval/documents.py`):

- the folded search copy of the stored text, never its displayed form;
- followed by the model-written concepts that describe it: the annotations of a verse (`quran_annotations`), the signals of a hadith (`hadith_signals`, shared by the parallel narrations of one hadith);
- for a hadith, the chain of narrators is left out when the text marks where it ends;
- capped in length, keeping the start, where a hadith's subject usually is.

A document is never shown. Its SHA-256 (`document_sha256`) is stored with each vector: a vector is stale when the document it was made from changes (a corrected verse, a new annotation), and the embedding step then computes it again, that document only.

Only our own store is embedded: the Quran from quranpedia.net edition 2 and the nine hadith books from the open datasets (`docs/SOURCES-AND-LICENSES.md`). Nothing is fetched from dorar.net or any other site (decisions 18 and 19).

## Models

| Model                    | Provider         | Size | Role                                    | Verses | Hadiths |
| ------------------------ | ---------------- | ---- | --------------------------------------- | ------ | ------- |
| `text-embedding-3-large` | OpenAI           | 1536 | default (OpenAI)                        | 6,236  | 65,712  |
| `bge-m3`                 | OVH AI Endpoints | 1024 | default when `AI_PROVIDER=ovh`          | 6,236  | 65,712  |
| `text-embedding-3-small` | OpenAI           | 1536 | measured, not used (kept in the export) | 6,236  | 14,940  |

`text-embedding-3-large` is asked for 1536 dimensions instead of its native 3072: pgvector indexes vectors of up to 2,000 dimensions. Vectors live in `app.quran_verse_embeddings` and `app.hadith_embeddings`, one row per text, model and size, with a partial HNSW index per default model.

## How they were computed (2026-10-04)

`uv run python -m src.cli.embed_corpus [quran] [hadith] [--provider P] [--model M] [--dimensions N] [--collections a,b] [--batch-size N] [--concurrency N] [--max-cost USD] [--dry-run]`

Every run is logged in `app.embedding_runs` (documents, already present, embedded, tokens, cost, times, error). A run sends only documents that are new or changed, so a second run sends nothing and a stopped run resumes where it stopped. Each text was embedded **once**:

| Run | Corpus | Model                  | Embedded | Skipped (already there) | Cost    | Note                            |
| --- | ------ | ---------------------- | -------- | ----------------------- | ------- | ------------------------------- |
| 1   | quran  | bge-m3                 | 0        | 0                       | $0      | failed: size not set (HTTP 400) |
| 2   | quran  | bge-m3                 | 6,236    | 0                       | $0.0064 |                                 |
| 3   | hadith | bge-m3                 | 14,940   | 0                       | $0.0168 | benchmark subset                |
| 4   | quran  | text-embedding-3-small | 6,236    | 0                       | $0.0251 |                                 |
| 5   | hadith | text-embedding-3-small | 14,940   | 0                       | $0.0722 | benchmark subset                |
| 6   | quran  | text-embedding-3-large | 6,236    | 0                       | $0.1629 |                                 |
| 7   | hadith | text-embedding-3-large | 14,940   | 0                       | $0.4693 | benchmark subset                |
| 8   | hadith | text-embedding-3-large | 50,772   | 14,940                  | $1.2340 | the rest of the nine books      |
| 9   | hadith | bge-m3                 | 0        | 14,940                  | $0      | stopped by a machine restart    |
| 10  | hadith | bge-m3                 | 175      | 14,940                  | $0.0002 | timed out; the 175 were kept    |
| 11  | hadith | bge-m3                 | 50,597   | 15,115                  | $0.0439 | the rest                        |

Total **$2.03**, about 38 minutes of wall time. The archive's `manifest.json` carries this log.

## The archive

`tabsira-vectors-<YYYY-MM-DD>.tar.gz` holds:

- `quran_verse_embeddings.tsv` and `hadith_embeddings.tsv`: one line per vector, `surah ayah text_sha256 model dimensions document_sha256 embedding` and `collection number text_sha256 model dimensions document_sha256 embedding` (PostgreSQL text format). Keys are natural keys, so the archive works on any database whatever its internal ids;
- `manifest.json`: counts per model, fingerprints of the stored Quran and hadith texts, and the runs that made the vectors;
- `SHA256SUMS`, `README.txt` and `import.sh`.

Current archive: `tabsira-vectors-2026-10-04.tar.gz`, 929 MB, 165,072 vectors (18,708 verse rows, 146,364 hadith rows), SHA-256 `aca79a6d46eee5bed8d6b2a16c726f279c3af5a52651b3fc1ba362aac7c052d4`. It is kept in the owners' S3 storage (MinIO, region europe), bucket `tabsira`, prefix `vectors/`, next to its `.tar.gz.sha256`, and is publicly readable:

- `https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz`
- `https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz.sha256`

Verified 2026-10-04 16:37 (Tunis): the downloaded archive matches its SHA-256 and every file inside matches `SHA256SUMS` (task 05.5). The bucket also holds the unpacked folder `vectors/tabsira-vectors-2026-10-04/`; the archive alone is enough. It is never committed (AGENTS.md: no corpora over 5 MB in git).

## Import (development and production)

1. The database has the scripture store (`make data`) and the app migrations, including the retrieval tables.
2. `curl -fO https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz -fO https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz.sha256 && sha256sum -c tabsira-vectors-2026-10-04.tar.gz.sha256` (about 1 min 30 s from Tunis).
3. `tar -xzf tabsira-vectors-2026-10-04.tar.gz && cd tabsira-vectors-2026-10-04`
4. `DATABASE_URL=postgresql://user:password@127.0.0.1:5432/tabsira ./import.sh` (the SQLAlchemy `postgresql+asyncpg://` form is accepted too).

The import checks `SHA256SUMS`, then attaches each vector to its verse by (surah, ayah) and to its hadith by (collection, number), **only when the stored text's SHA-256 is the one it was computed from**; anything else is skipped and counted, never forced. Existing rows are kept. It prints a table per model: in the archive, imported, skipped because the text changed, skipped because the text is not in the store. Rehearsed on 2026-10-04: 2 min 40 s for the rows it had to restore, exact rows restored.

After an import, `embed_corpus` computes only the vectors that are missing or whose document changed (a newer annotation import, a corrected verse).

## A new export

When the store, its annotations or the models change enough to matter, compute what changed with `embed_corpus`, then:

`DATABASE_URL=postgresql://... scripts/vectors/export.sh [OUT_DIR]`

It writes `tabsira-vectors-<today>.tar.gz` and its `.sha256` next to the checkout (`../tabsira-data/vectors` by default), every model and size included. Upload both to `vectors/` in the bucket, keep the previous archive until the new one is verified, and update this page's "Current archive" line. `scripts/vectors/import.sh` is the copy that goes into each archive.
