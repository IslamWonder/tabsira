#!/usr/bin/env bash
# Make sure GeoNames (the `geodata` schema, the places of the atlas) is in the
# database, from one of two sources (decision 57):
#
#   dump       (default) the verified snapshot of 2026-10-04 in the owners' bucket,
#              a pg_dump of the schema: about 340 MB, a few minutes, no third party
#   geonames   the original process, scripts/seed-geonames.sh: a fresh import from
#              geonames.org, which downloads about 600 MB and takes about 15 minutes
#
# Once only, whatever the source: when geodata.geonames holds places it does
# nothing, unless --force.
#
# The dump comes from, in this order:
#   GEODATA_DUMP       a local tabsira-geodata-<date>.dump (checked against the
#                      .sha256 beside it when there is one)
#   GEODATA_DUMP_URL   its address (default: the owners' bucket), downloaded once
#                      into GEODATA_DIR (default ../tabsira-data/geodata beside the
#                      checkout) and checked against its .sha256
# Only the rows are restored, into the tables `make migrate` made: one transaction
# empties them, drops their plain indexes, loads the rows with pg_restore, builds
# the indexes again and commits. The geodata chain's alembic_version is never
# touched, and a failure leaves the previous rows as they were.
#
# Usage: scripts/geodata/ensure.sh [--force] [--geonames-source=dump|geonames]
#   --force                  import again even when places are there (also DATA_FORCE=true)
#   --geonames-source=...    the source; GEONAMES_SOURCE sets the same (default dump)
# The database and the keys above are read from the environment first, then from
# the root .env.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib.sh
source "$REPO_ROOT/scripts/lib.sh"
# shellcheck source=../geonames-common.sh
source "$REPO_ROOT/scripts/geonames-common.sh"

load_env_keeping DATABASE_URL SYNC_DATABASE_URL GEODATA_DUMP GEODATA_DUMP_URL GEODATA_DIR GEONAMES_SOURCE

FORCE="${DATA_FORCE:-false}"
SOURCE="${GEONAMES_SOURCE:-dump}"
while [[ $# -gt 0 ]]; do
	case "$1" in
	--force) FORCE=true ;;
	--geonames-source=*) SOURCE="${1#*=}" ;;
	--geonames-source)
		[[ $# -ge 2 ]] || die "--geonames-source needs dump or geonames"
		SOURCE="$2"
		shift
		;;
	*) die "unknown argument: $1 (--force, --geonames-source=dump|geonames)" ;;
	esac
	shift
done
case "$SOURCE" in
dump | geonames) ;;
*) die "unknown GeoNames source '$SOURCE': dump or geonames" ;;
esac

DEFAULT_URL="https://s3-v2.riastorage.com/tabsira/geodata/tabsira-geodata-2026-10-04.dump"
GEODATA_DUMP="${GEODATA_DUMP:-}"
GEODATA_DUMP_URL="${GEODATA_DUMP_URL:-$DEFAULT_URL}"
GEODATA_DIR="${GEODATA_DIR:-$REPO_ROOT/../tabsira-data/geodata}"

require_cmd psql "Install the PostgreSQL client."
geonames_resolve_database
geonames_require_schema

places="$(geonames_psql -tA -c "SELECT count(*) FROM geodata.geonames")"
if [[ "$places" != "0" && "$FORCE" != "true" ]]; then
	ok "GeoNames already imported ($places places in $DB_NAME): nothing to do. Use --force to import again."
	exit 0
fi

if [[ "$SOURCE" == "geonames" ]]; then
	log "GeoNames from geonames.org (about 600 MB to download, about 15 minutes)"
	force_arg=()
	[[ "$FORCE" == "true" ]] && force_arg=(--force)
	SYNC_DATABASE_URL="$PSQL_URL" exec bash "$REPO_ROOT/scripts/seed-geonames.sh" "${force_arg[@]+"${force_arg[@]}"}"
fi

require_cmd pg_restore "Install the PostgreSQL client."
require_cmd sha256sum "Install coreutils."

# check_sha256 FILE: true when FILE.sha256 is beside it and matches.
check_sha256() {
	(cd "$(dirname "$1")" && sha256sum --check --quiet "$(basename "$1").sha256")
}

if [[ -n "$GEODATA_DUMP" ]]; then
	[[ -f "$GEODATA_DUMP" ]] || die "GEODATA_DUMP=$GEODATA_DUMP is not a file."
	dump="$GEODATA_DUMP"
	if [[ -f "$dump.sha256" ]]; then
		check_sha256 "$dump" || die "$dump does not match its .sha256."
		ok "Dump verified against its .sha256"
	else
		warn "No $(basename "$dump").sha256 beside $dump: restoring it unverified."
	fi
else
	require_cmd curl "Install curl."
	mkdir -p "$GEODATA_DIR"
	dump="$GEODATA_DIR/$(basename "$GEODATA_DUMP_URL")"
	if [[ -f "$dump" && -f "$dump.sha256" ]] && check_sha256 "$dump"; then
		log "Dump already downloaded and verified: $dump"
	else
		log "Downloading GeoNames (about 340 MB) from $GEODATA_DUMP_URL ..."
		curl -fL --retry 3 -o "$dump.sha256" "$GEODATA_DUMP_URL.sha256"
		curl -fL --retry 3 -C - -o "$dump" "$GEODATA_DUMP_URL"
		check_sha256 "$dump" || die "$dump does not match its .sha256: delete it and run again."
		ok "Dump verified against its .sha256"
	fi
fi

TABLES=(geonames geonames_alternate_names geonames_hierarchy geonames_country_info geonames_postal_codes)
toc="$(mktemp)"
trap 'rm -f "$toc" "$toc.list"' EXIT
pg_restore -l "$dump" >"$toc" || die "$dump is not a pg_dump archive."
: >"$toc.list"
for table in "${TABLES[@]}"; do
	grep -E "^[0-9]+; [0-9]+ [0-9]+ TABLE DATA geodata $table( |$)" "$toc" >>"$toc.list" ||
		die "$dump holds no data for geodata.$table."
done
grep -E "^[0-9]+; [0-9]+ [0-9]+ SEQUENCE SET geodata " "$toc" >>"$toc.list" || true

dump_revision="$(pg_restore --data-only -t alembic_version -f - "$dump" | awk '/^COPY /{getline; print $1; exit}')"
db_revision="$(geonames_psql -tA -c "SELECT version_num FROM geodata.alembic_version")"
[[ "$dump_revision" == "$db_revision" ]] ||
	warn "The dump was made at geodata revision ${dump_revision:-unknown}, the database is at $db_revision: the restore fails as a whole if the tables differ."

banner "GeoNames from $(basename "$dump") into $DB_NAME"
started=$SECONDS
{
	echo "\\ir $SCRIPT_DIR/restore-begin.sql"
	pg_restore --data-only -L "$toc.list" -f - "$dump"
	echo "\\ir $SCRIPT_DIR/restore-end.sql"
	geonames_sql_analyze | sed 's/^ANALYZE /ANALYZE geodata./'
} | geonames_psql -q >/dev/null

log "Summary"
{
	echo "SET search_path TO geodata, public;"
	geonames_sql_summary
} | geonames_psql -q -f -
places="$(geonames_psql -tA -c "SELECT count(*) FROM geodata.geonames")"
[[ "$places" != "0" ]] || die "The restore left geodata.geonames empty."
ok "GeoNames installed from the dump in $((SECONDS - started)) s ($places places)."
