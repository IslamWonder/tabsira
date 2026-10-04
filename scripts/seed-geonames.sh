#!/usr/bin/env bash
# Import GeoNames into the geodata schema: the places, their Arabic and English
# names, the hierarchy and the country information. It replaces what the tables
# held, in one transaction, so a run that fails changes nothing. For a live
# database, the monthly reconciliation is scripts/update-geonames.sh.
#
# Usage: scripts/seed-geonames.sh [--limit N] [--postal-codes]
#   --limit N        keep N places only: every country and first-level region
#                    first, then the most populated places. For CI and quick
#                    local runs; the full import is several million rows.
#   --postal-codes   also import the postal codes (skipped by default; the
#                    atlas does not use them)
#
# The downloads are cached in data/cache/geonames (GEONAMES_CACHE_DIR). A file is
# reused while its .done marker exists; delete the marker to download it again.
# An interrupted download resumes where it stopped. In CI a cached file older
# than a day is downloaded again (GEONAMES_MAX_AGE_DAYS changes that).
#
# The database is SYNC_DATABASE_URL or DATABASE_URL, from the environment first
# and the root .env after it. Run `make migrate` before it.
#
# Needs: psql, curl, unzip, awk, sort.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/geonames-common.sh"

LIMIT_ROWS=""
WITH_POSTAL=false

usage() {
	sed -n '2,/^set -Eeuo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--limit)
		[[ $# -ge 2 ]] || die "--limit needs a number"
		LIMIT_ROWS="$2"
		shift 2
		;;
	--limit=*)
		LIMIT_ROWS="${1#*=}"
		shift
		;;
	--postal-codes)
		WITH_POSTAL=true
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*) die "unknown argument: $1 (see --help)" ;;
	esac
done
if [[ -n "$LIMIT_ROWS" && ! "$LIMIT_ROWS" =~ ^[1-9][0-9]*$ ]]; then
	die "--limit must be a positive whole number (got '$LIMIT_ROWS')"
fi

for tool in psql curl unzip awk sort cut; do
	require_cmd "$tool" "It is needed to import GeoNames."
done
geonames_resolve_database
geonames_require_schema

if in_ci; then
	export GEONAMES_MAX_AGE_DAYS="${GEONAMES_MAX_AGE_DAYS:-1}"
fi

TMP_DIR="$(mktemp -d "${GEONAMES_TMP_DIR:-${TMPDIR:-/tmp}}/geonames.XXXXXX")"
cleanup() {
	rm -rf "$TMP_DIR"
}
trap cleanup EXIT

started="$(date +%s)"

# ── 1. Download ─────────────────────────────────────────────────────
banner "GeoNames import into $DB_NAME"
log "Phase 1: the downloads"
geonames_fetch "$GEONAMES_DUMP_URL/allCountries.zip" "$GEONAMES_CACHE_DIR/allCountries.zip"
geonames_fetch "$GEONAMES_DUMP_URL/alternateNamesV2.zip" "$GEONAMES_CACHE_DIR/alternateNamesV2.zip"
geonames_fetch "$GEONAMES_DUMP_URL/hierarchy.zip" "$GEONAMES_CACHE_DIR/hierarchy.zip"
geonames_fetch "$GEONAMES_DUMP_URL/countryInfo.txt" "$GEONAMES_CACHE_DIR/countryInfo.txt"
if $WITH_POSTAL; then
	geonames_fetch "$GEONAMES_ZIP_URL/allCountries.zip" "$GEONAMES_CACHE_DIR/postalCodes.zip"
fi

# ── 2. Extract ──────────────────────────────────────────────────────
log "Phase 2: filtering the dumps"
geonames_extract_places "$TMP_DIR/places.txt" "$LIMIT_ROWS"
PLACES_TOTAL="$(wc -l <"$TMP_DIR/places.txt" | tr -d ' ')"
[[ "$PLACES_TOTAL" -gt 0 ]] || die "No places were extracted; the dump format may have changed."
log "Places (feature classes P and A${LIMIT_ROWS:+, limited to $LIMIT_ROWS}): $PLACES_TOTAL"
geonames_extract_alternate_names "$TMP_DIR/alternate_names.txt"
geonames_extract_hierarchy "$TMP_DIR/hierarchy.txt"
geonames_extract_country_info "$TMP_DIR/country_info.txt"
if $WITH_POSTAL; then
	geonames_extract_postal_codes "$TMP_DIR/postal_codes.txt"
fi

# ── 3. Load, in one transaction ─────────────────────────────────────
log "Phase 3: loading into PostgreSQL"
{
	geonames_sql_stage
	cat <<'SQL'
TRUNCATE geonames_hierarchy, geonames_alternate_names, geonames_country_info, geonames;
INSERT INTO geonames
SQL
	geonames_sql_place_columns
	cat <<'SQL'
;
INSERT INTO geonames_alternate_names
  (alternate_name_id, geoname_id, iso_language, alternate_name,
   is_preferred, is_short, is_colloquial, is_historic)
SELECT alternate_name_id, geoname_id, iso_language, alternate_name,
       is_preferred, is_short, is_colloquial, is_historic
FROM new_alt;
INSERT INTO geonames_hierarchy (parent_id, child_id, hierarchy_type)
SELECT parent_id, child_id, hierarchy_type FROM new_hier;
SQL
	geonames_sql_upsert_countries
	if $WITH_POSTAL; then
		cat <<SQL
TRUNCATE geonames_postal_codes;
CREATE TEMP TABLE stage_postal (
  country_code TEXT, postal_code TEXT, place_name TEXT, admin_name1 TEXT,
  admin_code1 TEXT, admin_name2 TEXT, admin_code2 TEXT, admin_name3 TEXT,
  admin_code3 TEXT, latitude FLOAT8, longitude FLOAT8, accuracy INT
) ON COMMIT DROP;
\copy stage_postal FROM '${TMP_DIR}/postal_codes.txt' WITH (FORMAT csv, DELIMITER E'\t', QUOTE E'\b', ESCAPE E'\b', NULL '')
INSERT INTO geonames_postal_codes
  (country_code, postal_code, place_name, admin_name1, admin_code1, admin_name2,
   admin_code2, admin_name3, admin_code3, latitude, longitude, accuracy)
SELECT country_code, postal_code, place_name, admin_name1, admin_code1, admin_name2,
       admin_code2, admin_name3, admin_code3, latitude, longitude, accuracy
FROM stage_postal;
SQL
	fi
	echo "COMMIT;"
	geonames_sql_analyze
} | geonames_psql -f -

# ── 4. Summary ──────────────────────────────────────────────────────
log "Summary"
geonames_sql_summary | geonames_psql -f -

elapsed=$(($(date +%s) - started))
ok "GeoNames import complete in ${elapsed}s."

if in_ci; then
	mkdir -p "${WORKSPACE:-.}/.ci_metrics"
	printf '{"stage":"geonames","status":"passed","rows":%d}\n' "$PLACES_TOTAL" \
		>"${WORKSPACE:-.}/.ci_metrics/geonames.json"
fi
