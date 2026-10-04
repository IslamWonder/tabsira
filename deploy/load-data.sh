#!/usr/bin/env bash
# Load the reference data into the production database, once, after the first
# deploy has migrated it: the scripture store, the scripture vectors, the world
# ontology and the learning path (scripts/data.sh), and with --geonames the places
# of the atlas. Then prove it by counting what is in the three schemas.
#
# The database has three schemas, one Alembic chain each: `app` (the application),
# `geodata` (GeoNames, reference data) and `vectors` (the scripture embeddings).
# The first deploy runs the migrations; this script fills them.
#
# Run as the application user, on the application host:
#   deploy/load-data.sh [--check] [--geonames] [--force]
#   --check      print the state of the schemas and what is loaded; change nothing
#   --geonames   also import GeoNames (several million rows, long; only for the atlas)
#   --force      import again what is already there
#
# Idempotent: data that is there is left alone. The two corpus files are not in git
# (docs/ASSET_MANIFEST.md): put them in CORPUS_DIR (default $APP_ROOT/shared/corpus).
# The vectors are downloaded from the owners' bucket and checked against their
# .sha256, never computed here (docs/EMBEDDINGS.md); VECTORS_DIR (default
# $APP_ROOT/shared/vectors) keeps the download outside the releases, which are pruned.

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-/etc/tabsira/deploy.env}"
if [[ -f "$DEPLOY_ENV_FILE" ]]; then
	set -a
	# shellcheck disable=SC1090
	. "$DEPLOY_ENV_FILE"
	set +a
fi
APP_ROOT="${APP_ROOT:-/opt/tabsira}"
CURRENT_LINK="${CURRENT_LINK:-$APP_ROOT/current}"
SHARED_DIR="${SHARED_DIR:-$APP_ROOT/shared}"
ENV_FILE="${ENV_FILE:-$SHARED_DIR/.env}"
CORPUS_DIR="${CORPUS_DIR:-$SHARED_DIR/corpus}"
VECTORS_DIR="${VECTORS_DIR:-$SHARED_DIR/vectors}"
EXTENSIONS="postgis vector timescaledb pg_trgm unaccent pgcrypto btree_gin btree_gist pg_stat_statements"

CHECK=false
GEONAMES=false
FORCE=false
for arg in "$@"; do
	case "$arg" in
	--check) CHECK=true ;;
	--geonames) GEONAMES=true ;;
	--force) FORCE=true ;;
	-h | --help)
		sed -n '2,/^set -Eeuo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'
		exit 0
		;;
	*) die "usage: load-data.sh [--check] [--geonames] [--force]" ;;
	esac
done

[[ -f "$ENV_FILE" ]] || die "No $ENV_FILE."
have psql || die "psql is not installed or not on the PATH of this user."
[[ "$(env_get "$ENV_FILE" ENVIRONMENT)" == "production" ]] || die "ENVIRONMENT in $ENV_FILE is not production."
db_url="$(env_get "$ENV_FILE" SYNC_DATABASE_URL)"
db_url="${db_url:-$(env_get "$ENV_FILE" DATABASE_URL)}"
db_url="${db_url/postgresql+asyncpg:/postgresql:}"
db_url="${db_url/postgresql+psycopg:/postgresql:}"
[[ -n "$db_url" ]] || die "No DATABASE_URL in $ENV_FILE."
query() { psql -X -q -tA -v ON_ERROR_STOP=1 "$db_url" -c "$1"; }
# A count that is 0 when the table does not exist yet.
count() { query "SELECT CASE WHEN to_regclass('$1') IS NULL THEN 0 ELSE (SELECT count(*) FROM $1) END"; }

PROBLEMS=0
bad() {
	err "$*"
	PROBLEMS=$((PROBLEMS + 1))
}

# ─── The three schemas and the extensions ───────────────────────────
banner "Schemas and extensions"
query "SELECT 1" >/dev/null || die "The database does not accept this login (see deploy/check.sh)."
for schema in app geodata vectors; do
	if [[ "$(query "SELECT count(*) FROM pg_namespace WHERE nspname = '$schema'")" == 1 ]]; then
		ok "schema $schema ($(query "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$schema'") tables)"
	else
		bad "schema $schema is missing: the first deploy creates it with the migrations"
	fi
done
for ext in $EXTENSIONS; do
	[[ "$(query "SELECT count(*) FROM pg_extension WHERE extname = '$ext'")" == 1 ]] || bad "extension $ext is missing: run deploy/provision-postgres.sh on the data host"
done
[[ "$(query "SELECT to_regclass('app.quran_verses') IS NOT NULL")" == t ]] ||
	bad "app.quran_verses does not exist: the migrations have not run; deploy first"
((PROBLEMS == 0)) || die "The database is not ready for the data (see above)."
ok "all nine extensions present; the migrations have run"

# ─── Load ───────────────────────────────────────────────────────────
if ! $CHECK; then
	[[ -d "$CURRENT_LINK" ]] || die "No release at $CURRENT_LINK: deploy first."
	for corpus in quran-annotations.json sunnah-enriched.json; do
		[[ -f "$CORPUS_DIR/$corpus" ]] ||
			die "$CORPUS_DIR/$corpus is missing. Copy it there (docs/ASSET_MANIFEST.md names its source and SHA-256)."
	done
	mkdir -p "$VECTORS_DIR"
	banner "Scripture store, vectors, ontology and learning path"
	force_arg=()
	$FORCE && force_arg=(--force)
	(cd "$CURRENT_LINK" && CORPUS_DIR="$CORPUS_DIR" VECTORS_DIR="$VECTORS_DIR" bash scripts/data.sh "${force_arg[@]}")
	if $GEONAMES; then
		banner "GeoNames"
		(cd "$CURRENT_LINK" && bash scripts/seed-geonames.sh "${force_arg[@]}")
	fi
fi

# ─── What is in the database now ────────────────────────────────────
banner "Loaded"
verses="$(count app.quran_verses)"
hadiths="$(count app.hadiths)"
annotations="$(count app.quran_annotations)"
signals="$(count app.hadith_signals)"
ontology="$(count app.ontology_entities)"
quran_vectors="$(count vectors.quran_verse_embeddings)"
hadith_vectors="$(count vectors.hadith_embeddings)"
places="$(count geodata.geonames)"
log "Quran verses          $verses (6236 expected)"
log "hadiths               $hadiths"
log "Quran annotations     $annotations"
log "hadith signals        $signals"
log "ontology entities     $ontology"
log "Quran vectors         $quran_vectors (all models)"
log "hadith vectors        $hadith_vectors (all models)"
log "GeoNames places       $places$($GEONAMES || echo ' (not requested)')"
((verses == 6236)) || bad "The Quran store holds $verses verses, not 6236."
((hadiths > 0)) || bad "No hadith is stored."
((annotations > 0 && signals > 0)) || bad "The annotations or hadith signals are missing."
((ontology > 0)) || bad "The world ontology is not loaded."
((quran_vectors >= verses && hadith_vectors >= hadiths)) || bad "The vectors do not cover the store: import them (VECTORS_ARCHIVE_URL in $ENV_FILE)."
if $GEONAMES; then
	((places > 0)) || bad "GeoNames is empty."
fi
if ((PROBLEMS > 0)); then
	die "$PROBLEMS item(s) to fix."
fi
ok "The database holds the data."
