#!/usr/bin/env bash
# Import TABSIRA's reference data (the `corpus` schema) from an archive made by
# scripts/corpus/export.sh (docs/CORPUS.md, decision 57).
#
# The target database must be migrated (make migrate): the corpus tables exist and
# match the archive's. The import
#   1. checks every file against SHA256SUMS and the dump against the manifest;
#   2. refuses a database whose corpus already holds verses, unless --force; with
#      --force it also refuses when rows outside `corpus` and `vectors` point at
#      corpus rows (an editor's ruling, a learner's state, a reviewed ontology
#      candidate), since replacing the corpus would lose them;
#   3. in one transaction: empties the corpus tables (with --force; the vectors of
#      the old texts go with them), restores the rows of the dump with pg_restore,
#      checks every verse, past verse and hadith against its stored hash
#      (encode(sha256(convert_to(text, 'UTF8')), 'hex') = text_sha256, the hash
#      src/scripture/text.py computes), checks the count and the fingerprint of
#      every table against the manifest, and rebuilds the verse spans (of both
#      spellings, task 05.9). A failed
#      check rolls everything back: the database is as it was;
#   4. prints what the corpus holds.
#
# Usage, from the extracted folder, or from anywhere with the folder or the
# .tar.gz as argument (a .tar.gz is checked against the .sha256 beside it and
# extracted next to it):
#   DATABASE_URL=postgresql://user:password@127.0.0.1:5432/tabsira ./import.sh [--force]
#   DATABASE_URL=... scripts/corpus/import.sh [--force] ../tabsira-data/corpus/tabsira-corpus-2026-10-04.tar.gz
#   (or set PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE instead of DATABASE_URL)
set -euo pipefail

say() { printf '[corpus] %s\n' "$*"; }
die() {
	printf '[corpus] error: %s\n' "$*" >&2
	exit 1
}

# Parents first: the restore walks this list forwards, the emptying backwards.
TABLES=(
	quran_surahs quran_verses quran_verse_history quran_verse_search quran_annotations
	hadith_collections hadiths hadith_search hadith_signals
	ontology_entities learning_path_versions learning_domains learning_units
)
# Tables an archive may or may not hold: restored when it does, emptied with --force
# either way. The leak guard's skeletons in today's spelling (task 05.9) came after
# the archive of 2026-10-04; make data derives them from the restored text when the
# archive lacks them (src.cli.import_scripture standard).
OPTIONAL_TABLES=(quran_verse_standard_guard)

FORCE=false
source_path=""
for arg in "$@"; do
	case "$arg" in
	--force) FORCE=true ;;
	-*) die "unknown option: $arg (only --force)" ;;
	*)
		[[ -z "$source_path" ]] || die "one archive or folder only"
		source_path="$arg"
		;;
	esac
done
source_path="${source_path:-$(dirname "$0")}"

for tool in psql pg_restore sha256sum; do
	command -v "$tool" >/dev/null || die "$tool is required"
done

if [[ -f "$source_path" ]]; then
	[[ "$source_path" == *.tar.gz ]] || die "$source_path is not a tabsira-corpus-<date>.tar.gz"
	command -v tar >/dev/null || die "tar is required"
	archive_dir="$(cd "$(dirname "$source_path")" && pwd)"
	archive_name="$(basename "$source_path")"
	if [[ -f "$archive_dir/$archive_name.sha256" ]]; then
		(cd "$archive_dir" && sha256sum --check --quiet "$archive_name.sha256") ||
			die "$source_path does not match its .sha256: download it again"
		say "archive verified against its .sha256"
	else
		say "no $archive_name.sha256 beside the archive: its contents are still checked against SHA256SUMS"
	fi
	folder="$archive_dir/${archive_name%.tar.gz}"
	rm -rf "$folder"
	tar -xzf "$source_path" -C "$archive_dir"
	source_path="$folder"
fi
cd "$source_path"

[[ -f SHA256SUMS && -f corpus.dump && -f manifest.json && -f state.sql && -f verify.sql && -f force-guard.sql ]] ||
	die "$(pwd) is not an extracted corpus archive"
say "checking the files against SHA256SUMS"
sha256sum --check --quiet SHA256SUMS || die "a file does not match SHA256SUMS; download the archive again"
dump_sha256="$(sha256sum corpus.dump | cut -d' ' -f1)"
grep -q "\"sha256\": \"$dump_sha256\"" manifest.json || die "corpus.dump is not the dump the manifest names"

# psql understands postgresql:// but not SQLAlchemy's postgresql+driver:// form.
url="${DATABASE_URL:-}"
url="${url/postgresql+asyncpg:/postgresql:}"
url="${url/postgresql+psycopg:/postgresql:}"
PSQL=(psql -X -v ON_ERROR_STOP=1 -q -tA)
[[ -n "$url" ]] && PSQL+=("$url")
query() { "${PSQL[@]}" -c "$1"; }

manifest="$(cat manifest.json)"
# The archive's tables and the database's must be the same set; the columns are
# checked by the restore itself, which fails as a whole on any difference.
missing="$(
	"${PSQL[@]}" -v manifest="$manifest" <<'SQL'
SELECT coalesce(string_agg(name, ' ' ORDER BY name), '')
FROM (
    SELECT jsonb_object_keys((:'manifest'::jsonb) -> 'tables') AS name
    EXCEPT
    SELECT tablename FROM pg_tables WHERE schemaname = 'corpus'
) AS absent
SQL
)"
[[ -z "$missing" ]] || die "the database has no corpus table for: $missing (run make migrate; is this archive older than the schema?)"
for table in "${TABLES[@]}"; do
	grep -q "\"$table\": {" manifest.json || die "the archive has no $table: it predates this import script"
done

verses="$(query "SELECT count(*) FROM corpus.quran_verses")"
held="$(query "SELECT $(printf "(SELECT count(*) FROM corpus.%s) + " "${TABLES[@]}")0")"
if [[ "$FORCE" != "true" ]]; then
	[[ "$verses" == "0" ]] ||
		die "corpus.quran_verses already holds $verses verses: nothing imported. Use --force to replace the whole corpus."
	[[ "$held" == "0" ]] ||
		die "the corpus is not empty ($held rows, a store imported from its sources?): nothing imported. Use --force to replace the whole corpus."
fi

say "restoring (one transaction; a failed check leaves the database as it was)"
toc="$(mktemp)"
trap 'rm -f "$toc" "$toc.list"' EXIT
pg_restore -l corpus.dump >"$toc"
: >"$toc.list"
for table in "${TABLES[@]}"; do
	grep -E "^[0-9]+; [0-9]+ [0-9]+ TABLE DATA corpus $table( |$)" "$toc" >>"$toc.list" ||
		die "corpus.dump holds no data for $table"
done
known=${#TABLES[@]}
for table in "${OPTIONAL_TABLES[@]}"; do
	if grep -E "^[0-9]+; [0-9]+ [0-9]+ TABLE DATA corpus $table( |$)" "$toc" >>"$toc.list"; then
		known=$((known + 1))
	fi
done
grep -E "^[0-9]+; [0-9]+ [0-9]+ SEQUENCE SET corpus " "$toc" >>"$toc.list" || true
data_entries="$(grep -cE "^[0-9]+; [0-9]+ [0-9]+ TABLE DATA corpus " "$toc")"
[[ "$data_entries" == "$known" ]] ||
	die "corpus.dump holds data for $data_entries tables, this script knows $known of them: use the import.sh of a newer checkout"

{
	echo "BEGIN;"
	# The scripture tables refuse writes outside an import (src/scripture/guard.py).
	echo "SET LOCAL tabsira.scripture_write = 'import';"
	if [[ "$FORCE" == "true" ]]; then
		echo "\\ir force-guard.sql"
		for table in "${OPTIONAL_TABLES[@]}"; do
			echo "DO \$\$ BEGIN IF to_regclass('corpus.$table') IS NOT NULL THEN DELETE FROM corpus.$table; END IF; END \$\$;"
		done
		for ((index = ${#TABLES[@]} - 1; index >= 0; index--)); do
			echo "DELETE FROM corpus.${TABLES[index]};"
		done
	fi
	pg_restore --data-only -L "$toc.list" -f - corpus.dump
	echo "SELECT set_config('tabsira.corpus_manifest', :'manifest', true);"
	echo "\\ir verify.sql"
	# An archive's own verify.sql may predate the spans over today's spelling.
	echo "DO \$\$ BEGIN IF to_regclass('corpus.quran_verse_standard_spans') IS NOT NULL THEN REFRESH MATERIALIZED VIEW corpus.quran_verse_standard_spans; END IF; END \$\$;"
	echo "COMMIT;"
} | "${PSQL[@]}" -v manifest="$manifest" >/dev/null

say "every verse and hadith matches its stored hash; every table matches the manifest"
for table in "${TABLES[@]}"; do
	query "ANALYZE corpus.$table" >/dev/null
done
query "SELECT format('%-24s %s', 'path version (active)', coalesce((SELECT path_version FROM corpus.learning_path_versions WHERE is_active), 'none'))"
for table in "${TABLES[@]}"; do
	query "SELECT format('%-24s %s', '$table', count(*)) FROM corpus.$table"
done
say "done"
