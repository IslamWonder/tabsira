#!/usr/bin/env bash
# Export TABSIRA's scripture embeddings into one archive that any installation can
# import instead of paying to compute them again (docs/EMBEDDINGS.md).
#
# Every model and size in the database is exported, used or not. Each vector is
# written with its natural key (surah and ayah; collection and number), the SHA-256
# of the stored text and of the retrieval document it was computed from, so an
# import can refuse what no longer matches. The archive holds the vectors, a
# manifest (counts, store fingerprints, the runs that made them), SHA256SUMS,
# README.txt and import.sh. It is never committed: it goes to the owners' storage.
#
# Usage: DATABASE_URL=postgresql://... scripts/vectors/export.sh [OUT_DIR]
#   OUT_DIR defaults to ../tabsira-data/vectors next to the checkout.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT_DIR="${1:-$ROOT/../tabsira-data/vectors}"
NAME="tabsira-vectors-$(date -u +%Y-%m-%d)"
DIR="$OUT_DIR/$NAME"

url="${DATABASE_URL:-}"
url="${url/postgresql+asyncpg:/postgresql:}"
url="${url/postgresql+psycopg:/postgresql:}"
PSQL=(psql -X -v ON_ERROR_STOP=1 -q)
[[ -n "$url" ]] && PSQL+=("$url")

[[ -e "$DIR" || -e "$DIR.tar.gz" ]] && {
	echo "$DIR already exists; move it away first" >&2
	exit 1
}
mkdir -p "$DIR"

echo "[vectors] exporting verses"
"${PSQL[@]}" -c "\\copy (SELECT v.surah, v.ayah, v.text_sha256, e.model, e.dimensions, e.document_sha256, e.embedding FROM app.quran_verse_embeddings e JOIN app.quran_verses v ON v.id = e.verse_id ORDER BY v.surah, v.ayah, e.model, e.dimensions) TO '$DIR/quran_verse_embeddings.tsv' WITH (FORMAT text)"
echo "[vectors] exporting hadiths"
"${PSQL[@]}" -c "\\copy (SELECT h.collection, h.number, h.text_sha256, e.model, e.dimensions, e.document_sha256, e.embedding FROM app.hadith_embeddings e JOIN app.hadiths h ON h.id = e.hadith_id ORDER BY h.collection, h.number, e.model, e.dimensions) TO '$DIR/hadith_embeddings.tsv' WITH (FORMAT text)"

echo "[vectors] writing the manifest"
"${PSQL[@]}" -tA >"$DIR/manifest.json" <<'SQL'
SELECT json_build_object(
  'created_at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  'source_database_revision', (SELECT version_num FROM app.alembic_version LIMIT 1),
  'quran', (SELECT json_agg(json_build_object('model', model, 'dimensions', dimensions, 'rows', n)) FROM (SELECT model, dimensions, count(*) n FROM app.quran_verse_embeddings GROUP BY 1, 2 ORDER BY 1, 2) x),
  'hadith', (SELECT json_agg(json_build_object('model', model, 'dimensions', dimensions, 'rows', n)) FROM (SELECT model, dimensions, count(*) n FROM app.hadith_embeddings GROUP BY 1, 2 ORDER BY 1, 2) x),
  'store', json_build_object(
     'verses', (SELECT count(*) FROM app.quran_verses),
     'hadiths', (SELECT count(*) FROM app.hadiths),
     'quran_text_fingerprint', (SELECT encode(sha256(string_agg(text_sha256, '' ORDER BY surah, ayah)::bytea), 'hex') FROM app.quran_verses),
     'hadith_text_fingerprint', (SELECT encode(sha256(string_agg(text_sha256, '' ORDER BY collection, number)::bytea), 'hex') FROM app.hadiths)),
  'runs', (SELECT json_agg(json_build_object('corpus', corpus, 'provider', provider, 'model', model, 'dimensions', dimensions, 'status', status, 'documents', documents, 'already_present', unchanged, 'embedded', embedded, 'input_tokens', input_tokens, 'cost_usd', round(cost_usd::numeric, 4), 'started_at', started_at, 'finished_at', finished_at) ORDER BY id) FROM app.embedding_runs)
);
SQL

cp "$HERE/import.sh" "$DIR/import.sh"
cat >"$DIR/README.txt" <<'TXT'
TABSIRA scripture embeddings

The vectors the insight engine searches with, for every Quran verse and hadith in
the store, so a new installation imports them instead of computing them again.
They depend only on the stored texts, their annotations and the embedding model;
nothing about any user is in this archive. docs/EMBEDDINGS.md in the repository
explains how they are made.

Contents: quran_verse_embeddings.tsv, hadith_embeddings.tsv, manifest.json (counts,
store fingerprints, the runs that made them), SHA256SUMS, import.sh.

Import (the database needs the scripture store and the retrieval tables):
  tar -xzf <archive>.tar.gz && cd <archive>
  DATABASE_URL=postgresql://user:password@127.0.0.1:5432/tabsira ./import.sh
A vector is imported only when its text is in the store with the same SHA-256;
others are skipped and counted, and existing rows are kept. The engine's embedding
step (python -m src.cli.embed_corpus) then computes only what is missing or changed.
TXT
(cd "$DIR" && sha256sum quran_verse_embeddings.tsv hadith_embeddings.tsv manifest.json import.sh README.txt >SHA256SUMS)

echo "[vectors] packing"
tar -C "$OUT_DIR" -czf "$DIR.tar.gz" "$NAME"
(cd "$OUT_DIR" && sha256sum "$NAME.tar.gz" >"$NAME.tar.gz.sha256")
echo "[vectors] done: $DIR.tar.gz"
cat "$DIR.tar.gz.sha256"
