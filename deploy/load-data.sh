#!/usr/bin/env bash
# Load the reference data into the production database, once, after the first
# deploy has migrated it, in this order (scripts/data.sh): GeoNames, the corpus
# (the scripture store, the world ontology and the learning path), the scripture
# vectors. Then prove it by counting what is in the four schemas.
#
# The database has four schemas: `app` (the application) and `corpus` (the
# reference data, decision 57) share the app chain; `geodata` (GeoNames) and
# `vectors` (the scripture embeddings) have one Alembic chain each. The first
# deploy runs the migrations; this script fills them.
#
# Run as the application user, on the application host:
#   deploy/load-data.sh [--check] [--no-geonames] [--geonames-source=dump|geonames] [--force]
#   --check            print the state of the schemas and what is loaded; change nothing
#   --no-geonames      leave GeoNames out (the atlas then finds no place)
#   --geonames-source  dump (default): the verified 2026-10-04 snapshot from the owners'
#                      bucket, about 340 MB; geonames: a fresh import from geonames.org,
#                      about 600 MB to download and about 15 minutes. GEONAMES_SOURCE in
#                      the .env sets the same.
#   --force            install again what is already there
#   (--geonames, the old switch, is accepted: GeoNames is now loaded by default)
#
# Idempotent: data that is there is left alone. Nothing is fetched from the
# third-party sources: the corpus archive (CORPUS_ARCHIVE_URL), the GeoNames dump
# (GEODATA_DUMP_URL) and the vectors (VECTORS_ARCHIVE_URL) come from the owners'
# bucket and are checked against their .sha256 (docs/CORPUS.md, docs/EMBEDDINGS.md).
# They are downloaded once into ~/tabsira-data/{corpus,geodata,vectors}, outside
# the clone (CORPUS_ARCHIVE_DIR, GEODATA_DIR, VECTORS_DIR). Only with
# CORPUS_ARCHIVE_URL empty is the store built from its sources, and then the two
# corpus files must be in CORPUS_DIR (default /opt/tabsira/data/corpus,
# docs/ASSET_MANIFEST.md).

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
ENV_FILE="${ENV_FILE:-$REPO_DIR/.env}"
CORPUS_DIR="${CORPUS_DIR:-$REPO_DIR/data/corpus}"
VECTORS_DIR="${VECTORS_DIR:-$HOME/tabsira-data/vectors}"
CORPUS_ARCHIVE_DIR="${CORPUS_ARCHIVE_DIR:-$HOME/tabsira-data/corpus}"
GEODATA_DIR="${GEODATA_DIR:-$HOME/tabsira-data/geodata}"
EXTENSIONS="postgis vector timescaledb pg_trgm unaccent pgcrypto btree_gin btree_gist pg_stat_statements"

CHECK=false
GEONAMES=true
GEONAMES_SOURCE_ARG=""
FORCE=false
for arg in "$@"; do
	case "$arg" in
	--check) CHECK=true ;;
	--geonames) GEONAMES=true ;;
	--no-geonames) GEONAMES=false ;;
	--geonames-source=*) GEONAMES_SOURCE_ARG="${arg#*=}" ;;
	--force) FORCE=true ;;
	-h | --help)
		sed -n '2,/^set -Eeuo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'
		exit 0
		;;
	*) die "usage: load-data.sh [--check] [--no-geonames] [--geonames-source=dump|geonames] [--force]" ;;
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

# ─── The four schemas and the extensions ────────────────────────────
banner "Schemas and extensions"
query "SELECT 1" >/dev/null || die "The database does not accept this login (see deploy/check.sh)."
for schema in app corpus geodata vectors; do
	if [[ "$(query "SELECT count(*) FROM pg_namespace WHERE nspname = '$schema'")" == 1 ]]; then
		ok "schema $schema ($(query "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$schema'") tables)"
	else
		bad "schema $schema is missing: the first deploy creates it with the migrations"
	fi
done
for ext in $EXTENSIONS; do
	[[ "$(query "SELECT count(*) FROM pg_extension WHERE extname = '$ext'")" == 1 ]] || bad "extension $ext is missing: run deploy/provision-postgres.sh on the data host"
done
[[ "$(query "SELECT to_regclass('corpus.quran_verses') IS NOT NULL")" == t ]] ||
	bad "corpus.quran_verses does not exist: the migrations have not run; deploy first"
((PROBLEMS == 0)) || die "The database is not ready for the data (see above)."
ok "all nine extensions present; the migrations have run"

# ─── Load ───────────────────────────────────────────────────────────
if ! $CHECK; then
	# The corpus files are needed only when the store is built from its sources.
	# A .env without CORPUS_ARCHIVE_URL gets the bucket's default; an empty one means "never download".
	if [[ -z "$(env_get "$ENV_FILE" CORPUS_ARCHIVE)" ]] && grep -q '^CORPUS_ARCHIVE_URL=' "$ENV_FILE" &&
		[[ -z "$(env_get "$ENV_FILE" CORPUS_ARCHIVE_URL)" ]]; then
		for corpus in quran-annotations.json sunnah-enriched.json; do
			[[ -f "$CORPUS_DIR/$corpus" ]] ||
				die "$CORPUS_DIR/$corpus is missing and CORPUS_ARCHIVE_URL is empty. Set CORPUS_ARCHIVE_URL (docs/CORPUS.md), or copy the file there (docs/ASSET_MANIFEST.md)."
		done
	fi
	mkdir -p "$VECTORS_DIR" "$CORPUS_ARCHIVE_DIR" "$GEODATA_DIR"
	banner "GeoNames, corpus, vectors"
	data_args=()
	$FORCE && data_args+=(--force)
	if $GEONAMES; then
		data_args+=(--geonames)
		[[ -n "$GEONAMES_SOURCE_ARG" ]] && data_args+=("--geonames-source=$GEONAMES_SOURCE_ARG")
	else
		data_args+=(--no-geonames)
	fi
	(cd "$REPO_DIR" && CORPUS_DIR="$CORPUS_DIR" VECTORS_DIR="$VECTORS_DIR" CORPUS_ARCHIVE_DIR="$CORPUS_ARCHIVE_DIR" \
		GEODATA_DIR="$GEODATA_DIR" bash scripts/data.sh "${data_args[@]}")
fi

# ─── What is in the database now ────────────────────────────────────
banner "Loaded"
verses="$(count corpus.quran_verses)"
hadiths="$(count corpus.hadiths)"
annotations="$(count corpus.quran_annotations)"
signals="$(count corpus.hadith_signals)"
ontology="$(count corpus.ontology_entities)"
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
learning="$(query "SELECT CASE WHEN to_regclass('corpus.learning_path_versions') IS NULL THEN '' ELSE coalesce((SELECT path_version FROM corpus.learning_path_versions WHERE is_active), '') END")"
log "learning path         ${learning:-none active}"
log "GeoNames places       $places$($GEONAMES || echo ' (--no-geonames)')"
((verses == 6236)) || bad "The Quran store holds $verses verses, not 6236."
((hadiths > 0)) || bad "No hadith is stored."
((annotations > 0 && signals > 0)) || bad "The annotations or hadith signals are missing."
((ontology > 0)) || bad "The world ontology is not loaded."
[[ -n "$learning" ]] || bad "No learning path version is active."
((quran_vectors >= verses && hadith_vectors >= hadiths)) || bad "The vectors do not cover the store: import them (VECTORS_ARCHIVE_URL in $ENV_FILE)."
if $GEONAMES; then
	((places > 0)) || bad "GeoNames is empty."
fi
if ((PROBLEMS > 0)); then
	die "$PROBLEMS item(s) to fix."
fi
ok "The database holds the data."
