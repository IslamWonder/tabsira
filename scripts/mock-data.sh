#!/usr/bin/env bash
# Put the mock members of plan 22 into the database, or take them out (decision 63).
#
# Usage: scripts/mock-data.sh <command> [source] [--allow-production]
#   import <source>   import the v1 file (a path or s3://bucket/key); a second run adds nothing
#   clean             delete every @mock.tabsira.invalid account and everything it owns
#   reset <source>    clean, then import: the way to replace one file by another
#   status            how many mock members, insights and posts the database holds
#
# Without a source, MOCK_FILE is read, then ../tabsira-data/mock/tabsira-mock-v1.json.
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
	sed -n '4,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
	exit 2
}

command="${1:-}"
[[ -n "$command" ]] || usage
shift

source_file=""
extra=()
for arg in "$@"; do
	case "$arg" in
	--allow-production) extra+=("$arg") ;;
	-*) die "unknown option: $arg" ;;
	*) source_file="$arg" ;;
	esac
done
if [[ -z "$source_file" ]]; then
	source_file="${MOCK_FILE:-$REPO_ROOT/../tabsira-data/mock/tabsira-mock-v1.json}"
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
    "mock_members": "SELECT count(*) FROM app.users WHERE email LIKE '%@mock.tabsira.invalid'",
    "mock_insights": (
        "SELECT count(*) FROM app.insights i JOIN app.users u ON u.id = i.user_id"
        " WHERE u.email LIKE '%@mock.tabsira.invalid'"
    ),
    "mock_posts": (
        "SELECT count(*) FROM app.posts p JOIN app.users u ON u.id = p.author_id"
        " WHERE u.email LIKE '%@mock.tabsira.invalid'"
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

check_source() {
	case "$source_file" in
	s3://*) ;;
	*) [[ -f "$source_file" ]] || die "No such file: $source_file" ;;
	esac
}

import_file() {
	check_source
	check_ready
	log "Importing $source_file"
	api -m src.cli.import_mock "$source_file" --i-understand "${extra[@]}"
}

clean() {
	log "Deleting every mock member and what they own"
	api -m src.cli.import_mock --clean --i-understand "${extra[@]}"
}

status() {
	local found
	found="$(counts)"
	printf 'mock members: %s, insights: %s, posts: %s\n' \
		"$(value_of "$found" mock_members)" "$(value_of "$found" mock_insights)" "$(value_of "$found" mock_posts)"
}

case "$command" in
import) import_file && status ;;
clean) clean && status ;;
reset)
	check_source
	clean
	import_file
	status
	;;
status) status ;;
*) usage ;;
esac
