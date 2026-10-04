#!/usr/bin/env bash
# Restore a dump made by deploy/backup-db.sh into a database.
# Ported from the reference project's scripts/restore-db.sh.
#
# It restores into a database you name. By default that is a NEW database
# (tabsira_restore), so the live one is never overwritten by accident; check it
# there, then swap names by hand. Restoring over the live database needs
# --into with its name and the word --yes-overwrite.
#
# Usage (on the data host, as root or postgres):
#   deploy/restore-db.sh DUMP_FILE [--into DB_NAME] [--yes-overwrite] [--dry-run]

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

DUMP="${1:-}"
[[ -n "$DUMP" && "$DUMP" != --* ]] || die "usage: restore-db.sh DUMP_FILE [--into DB_NAME] [--yes-overwrite] [--dry-run]"
shift
INTO="tabsira_restore"
OVERWRITE=false
LIVE_DB="${DB_NAME:-tabsira}"
while [[ $# -gt 0 ]]; do
	case "$1" in
	--into)
		INTO="${2:-}"
		shift 2
		;;
	--yes-overwrite)
		OVERWRITE=true
		shift
		;;
	--dry-run)
		set_dry_run
		shift
		;;
	*) die "Unknown option: $1" ;;
	esac
done

[[ "$INTO" =~ ^[a-z_][a-z0-9_]*$ ]] || die "--into must be a plain database name."
if [[ "$INTO" == "$LIVE_DB" && "$OVERWRITE" != "true" ]]; then
	die "$INTO is the live database. Pass --yes-overwrite if you mean it."
fi
is_dry || [[ -f "$DUMP" ]] || die "No such dump: $DUMP"

as_postgres() {
	if [[ "$(id -un)" == "postgres" ]]; then "$@"; else sudo -u postgres "$@"; fi
}

log "Restoring $DUMP into $INTO"
if [[ "$INTO" == "$LIVE_DB" ]]; then
	run as_postgres dropdb --if-exists "$INTO"
fi
run as_postgres createdb -E UTF8 "$INTO"
# The extensions are created first, by a superuser: pg_restore as the owner
# could not create postgis, timescaledb or the others.
for ext in postgis vector timescaledb pg_trgm unaccent pgcrypto btree_gin btree_gist pg_stat_statements; do
	run as_postgres psql -X -q -d "$INTO" -c "SET search_path = public; CREATE EXTENSION IF NOT EXISTS $ext;"
done
if is_dry; then
	run as_postgres pg_restore --no-owner --role="${DB_USER:-tabsira}" --dbname "$INTO" "$DUMP"
else
	# TimescaleDB wants this around a restore; errors about already existing
	# extension objects are expected and listed, not fatal.
	as_postgres psql -X -q -d "$INTO" -c "SELECT timescaledb_pre_restore();" || true
	as_postgres pg_restore --no-owner --role="${DB_USER:-tabsira}" --dbname "$INTO" "$DUMP" || warn "pg_restore reported errors; read them above."
	as_postgres psql -X -q -d "$INTO" -c "SELECT timescaledb_post_restore();" || true
fi
ok "Restored into $INTO. Check it, then point DATABASE_URL at it or rename it."
