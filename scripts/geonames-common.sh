#!/usr/bin/env bash
# Shared by seed-geonames.sh and update-geonames.sh: the download cache, the
# extraction of the GeoNames dumps and the SQL that stages them. Source it after
# lib.sh and the caller's own `set -Eeuo pipefail`; it runs nothing by itself.
#
# What is imported, and what is not (DECISIONS.md, decision 9: place search and
# reverse lookup run on our own database, so no geocoding request leaves it):
#   places      feature classes P (populated places) and A (administrative
#               divisions, countries included)
#   names       alternate names in Arabic (isolanguage ar) and English (en) only
#   hierarchy   parent/child pairs between the imported places
#   countries   countryInfo.txt
#   postal      only when the caller asks for it
# Every table is in the `geodata` schema; the scripts never touch `app`.
#
# shellcheck shell=bash
# shellcheck disable=SC2034  # the URLs are used by the scripts that source this file

GEONAMES_DUMP_URL="https://download.geonames.org/export/dump"
GEONAMES_ZIP_URL="https://download.geonames.org/export/zip"

# Where the downloads are kept between runs (gitignored with the rest of data/cache).
GEONAMES_CACHE_DIR="${GEONAMES_CACHE_DIR:-$REPO_ROOT/data/cache/geonames}"

# Column layout of allCountries.txt (tab-separated), 1-based as awk counts:
#   1 geonameid  2 name  3 asciiname  4 alternatenames  5 latitude  6 longitude
#   7 feature class  8 feature code  9 country code  10 cc2  11-14 admin1..admin4
#   15 population  16 elevation  17 dem  18 timezone  19 modification date

# DATABASE URL for psql, from the environment first and the root .env after it, so
# that a caller (a test, a pipeline) can point the script at another database
# without the .env overriding it. The password is never printed.
geonames_resolve_database() {
	local url="${SYNC_DATABASE_URL:-${DATABASE_URL:-}}"
	if [[ -z "$url" ]] && ! in_ci; then
		url="$(env_value "$REPO_ROOT/.env" SYNC_DATABASE_URL)"
		[[ -n "$url" ]] || url="$(env_value "$REPO_ROOT/.env" DATABASE_URL)"
	fi
	[[ -n "$url" ]] || die "DATABASE_URL is not set. Run scripts/setup-db.sh, which writes it into the root .env."
	# psql does not understand SQLAlchemy's driver suffix.
	PSQL_URL="${url/+asyncpg/}"
	PSQL_URL="${PSQL_URL/+psycopg/}"
	DB_NAME="${PSQL_URL##*/}"
	DB_NAME="${DB_NAME%%\?*}"
}

# geonames_psql [psql arguments]: psql on the target database, never reading ~/.psqlrc.
geonames_psql() {
	psql "$PSQL_URL" -X -v ON_ERROR_STOP=1 "$@"
}

# ─── Download cache ─────────────────────────────────────────────────

# A download is complete when its zip passes `unzip -t`, or, for a text file,
# when it has a line that is not a comment.
geonames_verify() {
	local file="$1" name="$2"
	case "$name" in
	*.zip) unzip -tq "$file" >/dev/null 2>&1 ;;
	*) grep -qv '^#' "$file" 2>/dev/null ;;
	esac
}

# geonames_fetch URL DEST: make DEST available, from the cache when it can.
#
# DEST is reused while DEST.done exists next to it, and, when
# GEONAMES_MAX_AGE_DAYS is set, while it is younger than that. A download goes
# to DEST.part, is resumed with `curl -C -` after an interruption, is checked,
# and only then renamed and marked done; so a cache entry is either complete or
# absent. To download a file again, delete its .done marker.
geonames_fetch() {
	local url="$1" dest="$2" name part max_age status
	name="$(basename "$dest")"
	part="${dest}.part"
	max_age="${GEONAMES_MAX_AGE_DAYS:-}"

	if [[ -f "$dest" && -f "${dest}.done" ]]; then
		if [[ -z "$max_age" || -z "$(find "$dest" -mmin "+$((max_age * 1440))" 2>/dev/null)" ]]; then
			log "Cache hit: $name (delete $name.done to download it again)"
			return 0
		fi
		log "Cache stale: $name is older than $max_age day(s)"
	elif [[ -f "$dest" ]]; then
		log "Cache entry $name has no .done marker; downloading it again"
	fi
	rm -f "$dest" "${dest}.done"

	mkdir -p "$(dirname "$dest")"
	for _ in 1 2; do
		local resume=()
		if [[ -s "$part" ]]; then
			log "Resuming $name from $(wc -c <"$part" | tr -d ' ') bytes"
			resume=(-C -)
		else
			log "Downloading $name"
		fi
		status=0
		# No --max-time: a dump is hundreds of megabytes and curl may take as long as it takes.
		curl -fL -# --connect-timeout 30 --retry 3 --retry-delay 5 \
			${resume[@]+"${resume[@]}"} -o "$part" "$url" || status=$?
		if [[ $status -ne 0 ]]; then
			die "Download of $name failed (curl exit $status). Run the script again to resume it."
		fi
		if geonames_verify "$part" "$name"; then
			mv "$part" "$dest"
			touch "${dest}.done"
			ok "Saved $name ($(wc -c <"$dest" | tr -d ' ') bytes)"
			return 0
		fi
		# Most likely a resumed download whose source changed in between.
		warn "$name is incomplete or corrupt; starting it again from the beginning"
		rm -f "$part"
	done
	die "$name is still corrupt after a second download. Check $url and the disk space."
}

# ─── Extraction ─────────────────────────────────────────────────────
# Each function streams from the cached archive into a file of the working
# directory; nothing is unpacked next to the cache.

# geonames_extract_places OUT [LIMIT]
#
# Without LIMIT: every place of feature class P or A. With LIMIT: at most that
# many places, in this order of priority: the countries and first-level regions
# (ADM1), so that a place can still name its region and its country; then the
# populated places by population; then the other administrative divisions that
# have a population. Rows with no population are left out of the sort, which is
# the bulk of the file.
geonames_extract_places() {
	local out="$1" limit="${2:-}"
	if [[ -z "$limit" ]]; then
		unzip -p "$GEONAMES_CACHE_DIR/allCountries.zip" allCountries.txt |
			awk -F'\t' '$7 == "P" || $7 == "A"' >"$out"
		return 0
	fi
	unzip -p "$GEONAMES_CACHE_DIR/allCountries.zip" allCountries.txt |
		awk -F'\t' -v OFS='\t' '
			$7 == "P" || $7 == "A" {
				if ($8 == "ADM1" || $8 ~ /^PCL(I|D|F|S|IX)?$/) priority = 2
				else if ($7 == "P") priority = 1
				else priority = 0
				if (priority == 2 || $15 + 0 > 0) print priority, $15 + 0, $0
			}' |
		LC_ALL=C sort -t "$(printf '\t')" -k1,1nr -k2,2nr |
		awk -v limit="$limit" 'NR <= limit' |
		cut -f3- >"$out"
}

# geonames_extract_alternate_names OUT: Arabic and English names of any place; the
# load keeps those of the places that were imported.
geonames_extract_alternate_names() {
	unzip -p "$GEONAMES_CACHE_DIR/alternateNamesV2.zip" alternateNamesV2.txt |
		awk -F'\t' '$3 == "ar" || $3 == "en"' >"$1"
}

geonames_extract_hierarchy() {
	unzip -p "$GEONAMES_CACHE_DIR/hierarchy.zip" hierarchy.txt >"$1"
}

# countryInfo.txt starts with a block of comment lines.
geonames_extract_country_info() {
	grep -v '^#' "$GEONAMES_CACHE_DIR/countryInfo.txt" | grep -v '^[[:space:]]*$' >"$1"
}

geonames_extract_postal_codes() {
	unzip -p "$GEONAMES_CACHE_DIR/postalCodes.zip" allCountries.txt >"$1"
}

# ─── SQL ────────────────────────────────────────────────────────────
# Both scripts build their SQL out of these pieces and send it to one psql
# session, in one transaction: a run that fails leaves the previous data as it was.
#
# The files are read with COPY ... FORMAT csv and a quote character that never
# occurs (backspace): the dumps hold quotes and backslashes in names, which the
# text format would read as escapes and the default csv quote as quoting.

# SQL: the staging tables, filled from the files in TMP_DIR, and the derived
# tables both scripts load from (new_places, new_alt, new_hier, new_country).
geonames_sql_stage() {
	cat <<SQL
SET search_path TO geodata, public;
SET synchronous_commit = off;
SET maintenance_work_mem = '256MB';
BEGIN;

CREATE TEMP TABLE stage_places (
  geoname_id INT, name TEXT, ascii_name TEXT, alternate_names TEXT,
  latitude FLOAT8, longitude FLOAT8, feature_class TEXT, feature_code TEXT,
  country_code TEXT, cc2 TEXT, admin1_code TEXT, admin2_code TEXT,
  admin3_code TEXT, admin4_code TEXT, population BIGINT, elevation INT,
  dem INT, timezone TEXT, modification_date DATE
) ON COMMIT DROP;
\copy stage_places FROM '${TMP_DIR}/places.txt' WITH (FORMAT csv, DELIMITER E'\t', QUOTE E'\b', ESCAPE E'\b', NULL '')

CREATE TEMP TABLE stage_alt (
  alternate_name_id INT, geoname_id INT, iso_language TEXT, alternate_name TEXT,
  is_preferred TEXT, is_short TEXT, is_colloquial TEXT, is_historic TEXT,
  from_period TEXT, to_period TEXT
) ON COMMIT DROP;
\copy stage_alt FROM '${TMP_DIR}/alternate_names.txt' WITH (FORMAT csv, DELIMITER E'\t', QUOTE E'\b', ESCAPE E'\b', NULL '')

CREATE TEMP TABLE stage_hier (parent_id INT, child_id INT, hierarchy_type TEXT) ON COMMIT DROP;
\copy stage_hier FROM '${TMP_DIR}/hierarchy.txt' WITH (FORMAT csv, DELIMITER E'\t', QUOTE E'\b', ESCAPE E'\b', NULL '')

CREATE TEMP TABLE stage_country (
  iso2 TEXT, iso3 TEXT, iso_numeric INT, fips TEXT, country_name TEXT,
  capital TEXT, area_km2 FLOAT8, population BIGINT, continent TEXT,
  top_level_domain TEXT, currency_code TEXT, currency_name TEXT,
  phone_prefix TEXT, postal_code_format TEXT, postal_code_regex TEXT,
  languages TEXT, geoname_id INT, neighbours TEXT, equivalent_fips TEXT
) ON COMMIT DROP;
\copy stage_country FROM '${TMP_DIR}/country_info.txt' WITH (FORMAT csv, DELIMITER E'\t', QUOTE E'\b', ESCAPE E'\b', NULL '')

ANALYZE stage_places;
ANALYZE stage_alt;

-- The names kept: Arabic and English, for places that were imported.
CREATE TEMP TABLE new_alt ON COMMIT DROP AS
SELECT alternate_name_id, geoname_id, iso_language, alternate_name,
       COALESCE(is_preferred = '1', false) AS is_preferred,
       COALESCE(is_short = '1', false) AS is_short,
       COALESCE(is_colloquial = '1', false) AS is_colloquial,
       COALESCE(is_historic = '1', false) AS is_historic
FROM stage_alt
WHERE alternate_name IS NOT NULL
  AND btrim(alternate_name) <> ''
  AND geoname_id IN (SELECT geoname_id FROM stage_places);

-- One Arabic label per place: a current, uncolloquial, preferred, full name
-- written in Arabic letters, the lowest id on a tie.
CREATE TEMP TABLE new_ar ON COMMIT DROP AS
SELECT DISTINCT ON (geoname_id) geoname_id, alternate_name AS ar_name
FROM new_alt
WHERE iso_language = 'ar' AND alternate_name ~ '[ء-ي]'
ORDER BY geoname_id, is_historic, is_colloquial, is_preferred DESC, is_short, alternate_name_id;

CREATE TEMP TABLE new_places ON COMMIT DROP AS
SELECT p.geoname_id, p.name, p.latitude, p.longitude, p.feature_class, p.feature_code,
       p.country_code, p.cc2, p.admin1_code, p.admin2_code, p.admin3_code, p.admin4_code,
       p.population, p.timezone, p.modification_date, a.ar_name
FROM stage_places p
LEFT JOIN new_ar a USING (geoname_id);

CREATE TEMP TABLE new_hier ON COMMIT DROP AS
SELECT DISTINCT ON (parent_id, child_id) parent_id, child_id, hierarchy_type
FROM stage_hier
WHERE parent_id IN (SELECT geoname_id FROM stage_places)
  AND child_id IN (SELECT geoname_id FROM stage_places)
ORDER BY parent_id, child_id, hierarchy_type;

-- The flag is the two regional-indicator letters of the country code.
CREATE TEMP TABLE new_country ON COMMIT DROP AS
SELECT iso2, iso3, iso_numeric, fips, country_name, capital, area_km2, population,
       continent, top_level_domain, currency_code, currency_name, phone_prefix,
       postal_code_format, languages,
       CASE WHEN geoname_id IN (SELECT geoname_id FROM stage_places) THEN geoname_id END AS geoname_id,
       neighbours, equivalent_fips,
       CHR(127397 + ASCII(SUBSTRING(iso2 FROM 1 FOR 1))) ||
       CHR(127397 + ASCII(SUBSTRING(iso2 FROM 2 FOR 1))) AS flag_emoji
FROM stage_country
WHERE iso2 IS NOT NULL AND btrim(iso2) <> '';

ANALYZE new_places;
SQL
}

# SQL: upsert the countries (the same for the first import and for the update).
geonames_sql_upsert_countries() {
	cat <<'SQL'
INSERT INTO geonames_country_info (
  iso2, iso3, iso_numeric, fips, country_name, capital, area_km2, population,
  continent, top_level_domain, currency_code, currency_name, phone_prefix,
  postal_code_format, languages, geoname_id, neighbours, equivalent_fips, flag_emoji
)
SELECT iso2, iso3, iso_numeric, fips, country_name, capital, area_km2, population,
       continent, top_level_domain, currency_code, currency_name, phone_prefix,
       postal_code_format, languages, geoname_id, neighbours, equivalent_fips, flag_emoji
FROM new_country
ON CONFLICT (iso2) DO UPDATE SET
  iso3 = EXCLUDED.iso3,
  iso_numeric = EXCLUDED.iso_numeric,
  fips = EXCLUDED.fips,
  country_name = EXCLUDED.country_name,
  capital = EXCLUDED.capital,
  area_km2 = EXCLUDED.area_km2,
  population = EXCLUDED.population,
  continent = EXCLUDED.continent,
  top_level_domain = EXCLUDED.top_level_domain,
  currency_code = EXCLUDED.currency_code,
  currency_name = EXCLUDED.currency_name,
  phone_prefix = EXCLUDED.phone_prefix,
  postal_code_format = EXCLUDED.postal_code_format,
  languages = EXCLUDED.languages,
  geoname_id = EXCLUDED.geoname_id,
  neighbours = EXCLUDED.neighbours,
  equivalent_fips = EXCLUDED.equivalent_fips,
  flag_emoji = EXCLUDED.flag_emoji;
SQL
}

# SQL: INSERT of the places, shared by the first import and the update. The
# geometry is made here, in the same statement, from the coordinates; zero is a
# coordinate, so only a missing one leaves it empty.
geonames_sql_place_columns() {
	cat <<'SQL'
(geoname_id, name, latitude, longitude, feature_class, feature_code, country_code, cc2,
 admin1_code, admin2_code, admin3_code, admin4_code, population, timezone,
 modification_date, is_active, location_geom, ar_name)
SELECT geoname_id, name, latitude, longitude, feature_class, feature_code, country_code, cc2,
       admin1_code, admin2_code, admin3_code, admin4_code, population, timezone,
       modification_date, true,
       CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL
            THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) END,
       ar_name
FROM new_places
SQL
}

# SQL: the tables of the dump, to ANALYZE once the data is committed.
geonames_sql_analyze() {
	cat <<'SQL'
ANALYZE geonames;
ANALYZE geonames_alternate_names;
ANALYZE geonames_hierarchy;
ANALYZE geonames_country_info;
SQL
}

# The row counts, for the end of a run.
geonames_sql_summary() {
	cat <<'SQL'
SELECT 'geonames (active)' AS table_name, COUNT(*) AS rows FROM geonames WHERE is_active
UNION ALL SELECT 'geonames (soft-deleted)', COUNT(*) FROM geonames WHERE NOT is_active
UNION ALL SELECT 'geonames (populated places)', COUNT(*) FROM geonames WHERE feature_class = 'P' AND is_active
UNION ALL SELECT 'geonames (administrative divisions)', COUNT(*) FROM geonames WHERE feature_class = 'A' AND is_active
UNION ALL SELECT 'geonames with an Arabic name', COUNT(*) FROM geonames WHERE ar_name IS NOT NULL AND is_active
UNION ALL SELECT 'geonames_alternate_names', COUNT(*) FROM geonames_alternate_names
UNION ALL SELECT 'geonames_hierarchy', COUNT(*) FROM geonames_hierarchy
UNION ALL SELECT 'geonames_country_info', COUNT(*) FROM geonames_country_info
UNION ALL SELECT 'geonames_postal_codes', COUNT(*) FROM geonames_postal_codes;
SQL
}
