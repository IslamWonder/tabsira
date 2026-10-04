#!/usr/bin/env bash
# Dump the TABSIRA database to a local directory and rotate old dumps.
# Backups are local, with rotation; there is no off-site upload.
#
# A compressed custom-format dump (restorable selectively with pg_restore) is
# verified with pg_restore --list before it is kept; an unreadable dump is
# worse than none because it is believed. The roles and their settings go to
# a globals file beside it. Dumps older than BACKUP_KEEP_DAYS are deleted, but
# the newest BACKUP_KEEP_MIN are always kept.
#
# On the data host it runs as `postgres` over the local socket (the nightly
# timer, installed by deploy/provision-data.sh). On the application host
# deploy.sh calls it with --url for a dump before a migration.
#
# Usage: deploy/backup-db.sh [--url POSTGRES_URL] [--dry-run]
# Environment: BACKUP_DIR (/var/backups/tabsira), BACKUP_KEEP_DAYS (14),
# BACKUP_KEEP_MIN (3), DB_NAME (tabsira).

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/tabsira}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
BACKUP_KEEP_MIN="${BACKUP_KEEP_MIN:-3}"
DB_NAME="${DB_NAME:-tabsira}"
URL=""

while [[ $# -gt 0 ]]; do
	case "$1" in
	--url)
		URL="${2:-}"
		shift 2
		;;
	--dry-run)
		set_dry_run
		shift
		;;
	*) die "usage: backup-db.sh [--url POSTGRES_URL] [--dry-run]" ;;
	esac
done

[[ "$BACKUP_KEEP_DAYS" =~ ^[1-9][0-9]*$ ]] || die "BACKUP_KEEP_DAYS must be a whole number of days."
[[ "$BACKUP_KEEP_MIN" =~ ^[1-9][0-9]*$ ]] || die "BACKUP_KEEP_MIN must be a whole number."
[[ "$DB_NAME" =~ ^[a-z_][a-z0-9_]*$ ]] || die "DB_NAME must be a plain identifier."

# pg_dump does not understand the SQLAlchemy driver suffix.
URL="${URL/postgresql+psycopg:/postgresql:}"
URL="${URL/postgresql+asyncpg:/postgresql:}"
target=("$DB_NAME")
[[ -z "$URL" ]] || target=("$URL")

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP="$BACKUP_DIR/$DB_NAME-$STAMP.dump"

if is_dry; then
	log "Would dump to $DUMP, verify it, then delete dumps older than $BACKUP_KEEP_DAYS days (keeping the newest $BACKUP_KEEP_MIN)."
	exit 0
fi

have pg_dump || die "pg_dump is not installed."
umask 027
mkdir -p "$BACKUP_DIR"

log "Dumping $DB_NAME to $DUMP"
pg_dump --format=custom --compress=zstd:3 --file="$DUMP.part" "${target[@]}"
if ! pg_restore --list "$DUMP.part" >/dev/null 2>&1; then
	rm -f "$DUMP.part"
	die "The dump failed verification and was discarded."
fi
mv "$DUMP.part" "$DUMP"

# Roles and their settings (the search_path) are not in a database dump. Only
# possible with superuser access, i.e. the nightly run on the data host.
if [[ -z "$URL" ]] && have pg_dumpall; then
	pg_dumpall --globals-only --file="$BACKUP_DIR/globals-$STAMP.sql" || warn "The globals dump failed."
fi

# Rotation: everything older than the window except the newest BACKUP_KEEP_MIN.
for old in $(find "$BACKUP_DIR" -maxdepth 1 -name "$DB_NAME-*.dump" -type f -mtime +"$BACKUP_KEEP_DAYS" | sort | awk -v keep="$BACKUP_KEEP_MIN" '{ line[NR] = $0 } END { for (i = 1; i <= NR - keep; i++) print line[i] }'); do
	rm -f "$old"
done
find "$BACKUP_DIR" -maxdepth 1 -name 'globals-*.sql' -type f -mtime +"$BACKUP_KEEP_DAYS" -delete

ok "Backup complete: $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1)); $(find "$BACKUP_DIR" -maxdepth 1 -name "$DB_NAME-*.dump" | wc -l | tr -d ' ') dump(s) kept"
