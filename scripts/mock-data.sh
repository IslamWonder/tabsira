#!/usr/bin/env bash
# Put the mock members of plan 23 into the database, or take them out (decision 66).
#
# Usage: scripts/mock-data.sh <command> [source] [--allow-production] [--also-dependent-rows] [--no-backup]
#   import <source>   import the v1 file (a path, an https URL or s3://bucket/key); a second run adds nothing
#   clean             delete every @mock.tabsira.me account and everything it owns; it stops when
#                     other members' rows depend on them, unless --also-dependent-rows is given
#   reset <source>    clean, then import: the way to replace one file by another
#   backup            dump the app schema (members and everything they own) to ../tabsira-data/backups
#   status            how many mock members, insights and posts the database holds
#
# Without a source, MOCK_FILE is read, then ../tabsira-data/mock/tabsira-mock-v1.json when it
# exists, else the published file in the owners' bucket (MOCK_DEFAULT_URL below).
# import, reset and clean first dump the app schema (not corpus, geodata or vectors, which are
# large and reinstalled from their archives), unless --no-backup is given.
# It never resets the database and never touches a real member's rows. Before importing it
# checks that the migrations ran and that the scripture store and GeoNames are installed,
# since an insight whose verse or hadith is not in the store is skipped and an atlas entry
# needs GeoNames for its place. On a production host pass --allow-production.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

usage() {
	sed -n '4,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
	exit 2
}

command="${1:-}"
[[ -n "$command" ]] || usage
shift

# The version 1 file the owners published (plan 23); public like the corpus archives.
MOCK_DEFAULT_URL="https://s3-v2.riastorage.com/tabsira/mock/tabsira-mock-v1.json"
LOCAL_FILE="$REPO_ROOT/../tabsira-data/mock/tabsira-mock-v1.json"
BACKUP_DIR="$REPO_ROOT/../tabsira-data/backups"
downloaded=""

source_file=""
backup=true
extra=()
clean_extra=()
for arg in "$@"; do
	case "$arg" in
	--allow-production) extra+=("$arg") ;;
	--also-dependent-rows) clean_extra+=("$arg") ;;
	--no-backup) backup=false ;;
	-*) die "unknown option: $arg" ;;
	*) source_file="$arg" ;;
	esac
done
if [[ -z "$source_file" ]]; then
	if [[ -n "${MOCK_FILE:-}" ]]; then
		source_file="$MOCK_FILE"
	elif [[ -f "$LOCAL_FILE" ]]; then
		source_file="$LOCAL_FILE"
	else
		source_file="$MOCK_DEFAULT_URL"
	fi
fi

load_env "$REPO_ROOT"
require_cmd uv

api() { (cd "$REPO_ROOT/apps/api" && uv run --quiet python "$@"); }

# One query through the API's own settings, so the script reads the database the API reads.
counts() {
	api - <<'PY'
import asyncio

from sqlalchemy import text

from src.database import get_engine

QUERIES = {
    "verses": "SELECT count(*) FROM corpus.quran_verses",
    "hadiths": "SELECT count(*) FROM corpus.hadiths",
    "places": "SELECT count(*) FROM geodata.geonames",
    "mock_members": "SELECT count(*) FROM app.users WHERE email LIKE '%@mock.tabsira.me'",
    "mock_insights": (
        "SELECT count(*) FROM app.insights i JOIN app.users u ON u.id = i.user_id"
        " WHERE u.email LIKE '%@mock.tabsira.me'"
    ),
    "mock_posts": (
        "SELECT count(*) FROM app.posts p JOIN app.users u ON u.id = p.author_id"
        " WHERE u.email LIKE '%@mock.tabsira.me'"
    ),
}


async def main() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        for name, query in QUERIES.items():
            try:
                value = (await connection.execute(text(query))).scalar_one()
            except Exception:  # noqa: BLE001 - a missing table reads as zero here
                await connection.rollback()
                value = 0
            print(f"{name}={value}")
    await engine.dispose()


asyncio.run(main())
PY
}

value_of() { printf '%s\n' "$1" | sed -n "s/^$2=//p"; }

check_ready() {
	log "Applying any missing migration"
	bash "$SCRIPT_DIR/migrate.sh"
	local found
	found="$(counts)"
	[[ "$(value_of "$found" verses)" -gt 0 ]] || die "The scripture store is empty: install it first (make data)."
	[[ "$(value_of "$found" hadiths)" -gt 0 ]] || die "The hadith store is empty: install it first (make data)."
	[[ "$(value_of "$found" places)" -gt 0 ]] || die "GeoNames is not installed: install it first (make data)."
	ok "Scripture store and GeoNames are installed"
}

# An https source is downloaded once into a temporary file, removed when the script ends.
fetch_source() {
	case "$source_file" in
	http://* | https://*)
		require_cmd curl
		downloaded="$(mktemp "${TMPDIR:-/tmp}/tabsira-mock.XXXXXX")"
		trap 'rm -f "$downloaded"' EXIT
		log "Downloading $source_file"
		curl -fsSL --retry 3 --max-time 300 -o "$downloaded" "$source_file" || die "Cannot download $source_file"
		source_file="$downloaded"
		ok "Downloaded $(wc -c <"$source_file" | tr -d ' ') bytes"
		;;
	esac
}

check_source() {
	fetch_source
	case "$source_file" in
	s3://*) ;;
	*) [[ -f "$source_file" ]] || die "No such file: $source_file" ;;
	esac
}

# pg_dump of the app schema only, with the API's own database address.
dump_app_schema() {
	require_cmd pg_dump
	mkdir -p "$BACKUP_DIR"
	local url target
	url="$(
		api - <<'PY'
from src.config import load_settings

settings = load_settings()
url = settings.sync_database_url or settings.database_url
print(url.get_secret_value().replace("+asyncpg", "").replace("+psycopg", ""))
PY
	)"
	target="$BACKUP_DIR/app-$(date -u +%Y%m%dT%H%M%SZ).dump"
	log "Backing up the app schema to $target"
	pg_dump --format=custom --schema=app --no-owner --file="$target" "$url" || die "The backup failed: nothing was changed."
	ok "Backup written ($(du -h "$target" | cut -f1)); restore with: pg_restore --clean --if-exists --schema=app -d <database> $target"
}

maybe_backup() {
	if [[ "$backup" == "true" ]]; then
		dump_app_schema
	else
		warn "No backup taken (--no-backup)"
	fi
}

import_file() {
	check_source
	check_ready
	log "Importing $source_file"
	api -m src.cli.import_mock "$source_file" --i-understand "${extra[@]}"
}

clean() {
	log "Deleting every mock member and what they own"
	api -m src.cli.import_mock --clean --i-understand "${extra[@]}" "${clean_extra[@]}"
}

status() {
	local found
	found="$(counts)"
	printf 'mock members: %s, insights: %s, posts: %s\n' \
		"$(value_of "$found" mock_members)" "$(value_of "$found" mock_insights)" "$(value_of "$found" mock_posts)"
}

case "$command" in
import)
	check_source
	maybe_backup
	import_file
	status
	;;
clean)
	maybe_backup
	clean
	status
	;;
reset)
	check_source
	maybe_backup
	clean
	import_file
	status
	;;
backup) dump_app_schema ;;
status) status ;;
*) usage ;;
esac
