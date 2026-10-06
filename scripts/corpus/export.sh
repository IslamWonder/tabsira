#!/usr/bin/env bash
# Export TABSIRA's reference data, the `corpus` schema, into one archive that any
# installation imports instead of rebuilding it from the third-party sources
# (docs/CORPUS.md, decision 57).
#
# The schema holds the Quran (surahs, verses, their history and search copies, the
# annotations), the hadiths (collections, texts, search copies, signals), the world
# ontology and the learning path. Nothing about any user is in it: rulings, the
# verification queue, the audit log, the sync state and every learner's state stay
# in `app` and are never exported.
#
# The archive holds corpus.dump (pg_dump -Fc --no-owner --no-privileges -n corpus),
# manifest.json (row counts, a fingerprint of every table, a fingerprint of the
# stored text hashes of the scripture tables, the dump's SHA-256, the Quran dump
# versions, the ontology's and the learning path's sources and the active path
# version), SHA256SUMS, README.txt, NOTICE.txt (the sources, their licences and
# the credit they ask for; filled with the quranpedia dump version), import.sh and the SQL it runs (state.sql,
# verify.sql, force-guard.sql). The state is read
# before and after the dump; an export that saw the data change in between (the
# daily Quran sync) stops, and is run again.
#
# Usage: DATABASE_URL=postgresql://... scripts/corpus/export.sh [OUT_DIR]
#   OUT_DIR defaults to ../tabsira-data/corpus next to the checkout. Never committed:
#   the owners upload tabsira-corpus-<date>.tar.gz and its .sha256 to their bucket.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT_DIR="${1:-$ROOT/../tabsira-data/corpus}"
NAME="tabsira-corpus-$(date -u +%Y-%m-%d)"
DIR="$OUT_DIR/$NAME"

say() { printf '[corpus] %s\n' "$*"; }
die() {
	printf '[corpus] error: %s\n' "$*" >&2
	exit 1
}

for tool in psql pg_dump pg_restore sha256sum tar; do
	command -v "$tool" >/dev/null || die "$tool is required"
done

# psql understands postgresql:// but not SQLAlchemy's postgresql+driver:// form.
url="${DATABASE_URL:-}"
url="${url/postgresql+asyncpg:/postgresql:}"
url="${url/postgresql+psycopg:/postgresql:}"
PSQL=(psql -X -v ON_ERROR_STOP=1 -q -tA)
DUMP=(pg_dump)
if [[ -n "$url" ]]; then
	PSQL+=("$url")
	DUMP+=(--dbname="$url")
fi

[[ "$("${PSQL[@]}" -c "SELECT to_regclass('corpus.quran_verses') IS NOT NULL")" == "t" ]] ||
	die "corpus.quran_verses is missing: this database is not migrated to the corpus schema (make migrate)"
[[ "$("${PSQL[@]}" -c "SELECT count(*) FROM corpus.quran_verses")" == "6236" ]] ||
	die "corpus.quran_verses does not hold the 6,236 verses: there is nothing whole to export"

state() { "${PSQL[@]}" -f "$HERE/state.sql" -c "SELECT pg_temp.corpus_state()"; }

[[ -e "$DIR" || -e "$DIR.tar.gz" ]] && die "$DIR already exists; move it away first"
mkdir -p "$DIR"

say "reading the state of the corpus schema"
before="$(state)"
say "dumping the corpus schema"
"${DUMP[@]}" -Fc --no-owner --no-privileges -n corpus -f "$DIR/corpus.dump"
after="$(state)"
[[ "$before" == "$after" ]] || {
	rm -rf "$DIR"
	die "the corpus changed while it was dumped (the Quran sync?); run the export again"
}
pg_restore -l "$DIR/corpus.dump" >/dev/null || die "pg_restore cannot read the dump it was given"
dump_sha256="$(sha256sum "$DIR/corpus.dump" | cut -d' ' -f1)"

say "writing the manifest"
"${PSQL[@]}" -v tables="$after" -v dump_sha256="$dump_sha256" >"$DIR/manifest.json" <<'SQL'
SELECT jsonb_pretty(jsonb_build_object(
  'format', 1,
  'created_at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  'source_app_revision', (SELECT version_num FROM app.alembic_version LIMIT 1),
  'postgres_version', current_setting('server_version'),
  'dump', jsonb_build_object('file', 'corpus.dump', 'sha256', :'dump_sha256'),
  'tables', :'tables'::jsonb,
  'quran_sources', (SELECT jsonb_agg(DISTINCT source_version) FROM corpus.quran_verses),
  'hadith_sources', (SELECT jsonb_agg(jsonb_build_object('collection', slug, 'dataset', source_dataset, 'version', source_version, 'file_sha256', source_sha256) ORDER BY display_order) FROM corpus.hadith_collections),
  'ontology_source_sha256', (SELECT jsonb_agg(DISTINCT source_sha256) FROM corpus.ontology_entities),
  'learning_path', jsonb_build_object(
     'active_version', (SELECT path_version FROM corpus.learning_path_versions WHERE is_active),
     'versions', (SELECT jsonb_agg(jsonb_build_object('path_version', path_version, 'version', version, 'source_file', source_file, 'source_sha256', source_sha256, 'domains', domain_count, 'units', unit_count, 'active', is_active) ORDER BY path_version COLLATE "C") FROM corpus.learning_path_versions))
));
SQL

cp "$HERE/import.sh" "$HERE/state.sql" "$HERE/verify.sql" "$HERE/force-guard.sql" "$DIR/"
# Republishing quranpedia's data as a dataset requires its credit, a link and the
# dump version; the Open-Hadith-Data rows carry the ODbL notice (docs/SOURCES-AND-LICENSES.md).
quranpedia_version="$("${PSQL[@]}" -c "SELECT string_agg(DISTINCT replace(source_version, 'dump:', ''), ', ') FROM corpus.quran_verses")"
[[ -n "$quranpedia_version" ]] || die "the corpus holds no Quran verse: nothing to credit, nothing to export"
sed "s/@QURANPEDIA_VERSION@/$quranpedia_version/" "$HERE/NOTICE.txt" >"$DIR/NOTICE.txt"
cat >"$DIR/README.txt" <<'TXT'
TABSIRA reference data (the `corpus` schema)

The Quran text of quranpedia's mushaf 2 with its history and search copies (and
the leak guard's skeletons of each verse in today's spelling, derived from it), the
annotated corpus used for retrieval, the nine hadith books with their search copies
and signals, the world ontology and the learning path, exactly as the database of
the installation that exported them holds them. Every verse and hadith carries the
SHA-256 of its UTF-8 bytes. Nothing about any user is in this archive.
docs/CORPUS.md in the repository explains how it is made.

Contents: corpus.dump (pg_dump custom format, schema corpus), manifest.json (counts,
fingerprints, sources, the learning path version), NOTICE.txt (the sources, their
licences and the credit they ask for: read it before you share this archive),
SHA256SUMS, import.sh and the SQL it runs (state.sql, verify.sql, force-guard.sql).

Import (the database must be migrated to the same corpus tables, make migrate):
  tar -xzf <archive>.tar.gz && cd <archive>
  DATABASE_URL=postgresql://user:password@127.0.0.1:5432/tabsira ./import.sh
It refuses a database whose corpus already holds verses unless --force is given,
restores the rows in one transaction, checks every stored text against its hash
and every table against the manifest, and changes nothing when a check fails.
TXT
(cd "$DIR" && sha256sum corpus.dump manifest.json import.sh state.sql verify.sql force-guard.sql README.txt NOTICE.txt >SHA256SUMS)

say "packing"
tar -C "$OUT_DIR" -czf "$DIR.tar.gz" "$NAME"
(cd "$OUT_DIR" && sha256sum "$NAME.tar.gz" >"$NAME.tar.gz.sha256")
say "done: $DIR.tar.gz"
cat "$DIR.tar.gz.sha256"
