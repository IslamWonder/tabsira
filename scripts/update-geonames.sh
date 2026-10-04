#!/usr/bin/env bash
# Monthly reconciliation of the GeoNames tables with a fresh dump, for a live
# database: places that disappeared are soft-deleted (is_active = false, never
# removed), places that came back are reactivated, new and changed ones are
# upserted, and the names, hierarchy and countries are brought in line. Readers
# keep working throughout: nothing is truncated, and it is one transaction.
#
# Usage: scripts/update-geonames.sh [--force]
#   --force   run even when the dump holds under half of the active places,
#             which is refused by default as the sign of a broken download
#
# Same filters as scripts/seed-geonames.sh (places of class P and A, names in
# Arabic and English). Postal codes are not touched. Meant for cron, on one
# machine only:
#   0 3 1 * * /path/to/scripts/update-geonames.sh >> /var/log/tabsira/geonames.log 2>&1
# The cache is refreshed when its files are over a day old (GEONAMES_MAX_AGE_DAYS).
#
# Needs: psql, curl, unzip, awk, sort.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/geonames-common.sh"

FORCE=false

usage() {
	sed -n '2,/^set -Eeuo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--force)
		FORCE=true
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*) die "unknown argument: $1 (see --help)" ;;
	esac
done

for tool in psql curl unzip awk sort cut; do
	require_cmd "$tool" "It is needed to update GeoNames."
done
geonames_resolve_database

export GEONAMES_MAX_AGE_DAYS="${GEONAMES_MAX_AGE_DAYS:-1}"

TMP_DIR="$(mktemp -d "${GEONAMES_TMP_DIR:-${TMPDIR:-/tmp}}/geonames.XXXXXX")"
cleanup() {
	rm -rf "$TMP_DIR"
}
trap cleanup EXIT

started="$(date +%s)"

# ── 1. Download ─────────────────────────────────────────────────────
banner "GeoNames update of $DB_NAME"
log "Step 1: the downloads"
geonames_fetch "$GEONAMES_DUMP_URL/allCountries.zip" "$GEONAMES_CACHE_DIR/allCountries.zip"
geonames_fetch "$GEONAMES_DUMP_URL/alternateNamesV2.zip" "$GEONAMES_CACHE_DIR/alternateNamesV2.zip"
geonames_fetch "$GEONAMES_DUMP_URL/hierarchy.zip" "$GEONAMES_CACHE_DIR/hierarchy.zip"
geonames_fetch "$GEONAMES_DUMP_URL/countryInfo.txt" "$GEONAMES_CACHE_DIR/countryInfo.txt"

# ── 2. Extract, and refuse a dump that looks broken ─────────────────
log "Step 2: filtering the dumps"
geonames_extract_places "$TMP_DIR/places.txt"
geonames_extract_alternate_names "$TMP_DIR/alternate_names.txt"
geonames_extract_hierarchy "$TMP_DIR/hierarchy.txt"
geonames_extract_country_info "$TMP_DIR/country_info.txt"

INCOMING="$(wc -l <"$TMP_DIR/places.txt" | tr -d ' ')"
ACTIVE="$(geonames_psql -tA -c "SELECT count(*) FROM geodata.geonames WHERE is_active")"
log "Places in the dump: $INCOMING; active in the database: $ACTIVE"
[[ "$INCOMING" -gt 0 ]] || die "The dump holds no places; the format may have changed. Nothing was changed."
if ! $FORCE && [[ "$ACTIVE" -gt 0 && $((INCOMING * 2)) -lt "$ACTIVE" ]]; then
	die "The dump holds under half of the $ACTIVE active places, which a good download never does. Nothing was changed. Use --force if it is right."
fi

# ── 3. Reconcile, in one transaction ────────────────────────────────
log "Step 3: reconciling"
{
	geonames_sql_stage
	cat <<'SQL'
-- Places missing from the dump are soft-deleted; those that reappear are
-- reactivated by the upsert below.
UPDATE geonames g SET is_active = false
WHERE g.is_active
  AND NOT EXISTS (SELECT 1 FROM new_places n WHERE n.geoname_id = g.geoname_id);

INSERT INTO geonames
SQL
	geonames_sql_place_columns
	cat <<'SQL'
ON CONFLICT (geoname_id) DO UPDATE SET
  name = EXCLUDED.name,
  latitude = EXCLUDED.latitude,
  longitude = EXCLUDED.longitude,
  feature_class = EXCLUDED.feature_class,
  feature_code = EXCLUDED.feature_code,
  country_code = EXCLUDED.country_code,
  cc2 = EXCLUDED.cc2,
  admin1_code = EXCLUDED.admin1_code,
  admin2_code = EXCLUDED.admin2_code,
  admin3_code = EXCLUDED.admin3_code,
  admin4_code = EXCLUDED.admin4_code,
  population = EXCLUDED.population,
  timezone = EXCLUDED.timezone,
  modification_date = EXCLUDED.modification_date,
  is_active = true,
  location_geom = EXCLUDED.location_geom,
  ar_name = EXCLUDED.ar_name
-- Rows that did not change are not rewritten.
WHERE (geonames.name, geonames.latitude, geonames.longitude, geonames.feature_class,
       geonames.feature_code, geonames.country_code, geonames.cc2, geonames.admin1_code,
       geonames.admin2_code, geonames.admin3_code, geonames.admin4_code, geonames.population,
       geonames.timezone, geonames.modification_date, geonames.is_active, geonames.ar_name)
  IS DISTINCT FROM
      (EXCLUDED.name, EXCLUDED.latitude, EXCLUDED.longitude, EXCLUDED.feature_class,
       EXCLUDED.feature_code, EXCLUDED.country_code, EXCLUDED.cc2, EXCLUDED.admin1_code,
       EXCLUDED.admin2_code, EXCLUDED.admin3_code, EXCLUDED.admin4_code, EXCLUDED.population,
       EXCLUDED.timezone, EXCLUDED.modification_date, true, EXCLUDED.ar_name);

-- Names: delete those that are gone, insert the new, change the changed.
DELETE FROM geonames_alternate_names a
WHERE NOT EXISTS (SELECT 1 FROM new_alt n WHERE n.alternate_name_id = a.alternate_name_id);
INSERT INTO geonames_alternate_names
  (alternate_name_id, geoname_id, iso_language, alternate_name,
   is_preferred, is_short, is_colloquial, is_historic)
SELECT alternate_name_id, geoname_id, iso_language, alternate_name,
       is_preferred, is_short, is_colloquial, is_historic
FROM new_alt
ON CONFLICT (alternate_name_id) DO UPDATE SET
  geoname_id = EXCLUDED.geoname_id,
  iso_language = EXCLUDED.iso_language,
  alternate_name = EXCLUDED.alternate_name,
  is_preferred = EXCLUDED.is_preferred,
  is_short = EXCLUDED.is_short,
  is_colloquial = EXCLUDED.is_colloquial,
  is_historic = EXCLUDED.is_historic
WHERE (geonames_alternate_names.geoname_id, geonames_alternate_names.iso_language,
       geonames_alternate_names.alternate_name, geonames_alternate_names.is_preferred,
       geonames_alternate_names.is_short, geonames_alternate_names.is_colloquial,
       geonames_alternate_names.is_historic)
  IS DISTINCT FROM
      (EXCLUDED.geoname_id, EXCLUDED.iso_language, EXCLUDED.alternate_name,
       EXCLUDED.is_preferred, EXCLUDED.is_short, EXCLUDED.is_colloquial, EXCLUDED.is_historic);

-- Hierarchy, the same way.
DELETE FROM geonames_hierarchy h
WHERE NOT EXISTS (
  SELECT 1 FROM new_hier n WHERE n.parent_id = h.parent_id AND n.child_id = h.child_id);
INSERT INTO geonames_hierarchy (parent_id, child_id, hierarchy_type)
SELECT parent_id, child_id, hierarchy_type FROM new_hier
ON CONFLICT (parent_id, child_id) DO UPDATE SET hierarchy_type = EXCLUDED.hierarchy_type
WHERE geonames_hierarchy.hierarchy_type IS DISTINCT FROM EXCLUDED.hierarchy_type;
SQL
	geonames_sql_upsert_countries
	echo "COMMIT;"
	geonames_sql_analyze
} | geonames_psql -f -

# ── 4. Summary ──────────────────────────────────────────────────────
log "Summary"
geonames_sql_summary | geonames_psql -f -

elapsed=$(($(date +%s) - started))
ok "GeoNames update complete in ${elapsed}s ($(date -u +%Y-%m-%dT%H:%M:%SZ))."
