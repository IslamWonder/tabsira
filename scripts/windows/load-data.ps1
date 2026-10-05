<#
Load the reference data into this machine's database, once, and prove it: what
deploy/load-data.sh does on the production host, for a native Windows
development or test machine. The two files change together.

In this order (scripts\data.ps1): GeoNames, the corpus (the scripture store, the
world ontology and the learning path, decision 57), the scripture vectors. Then
it counts what is in the four schemas and says what is missing.

Usage: scripts\windows\load-data.ps1 [-Check] [-NoGeonames] [-GeonamesSource dump|geonames] [-Force]
  -Check            print the state of the schemas and what is loaded; change nothing
  -NoGeonames       leave GeoNames out (the atlas then finds no place)
  -GeonamesSource   dump (default): the verified snapshot from the owners' bucket,
                    about 340 MB. geonames (a fresh import from geonames.org) has no
                    Windows counterpart: scripts\data.ps1 says so and stops.
  -Force            install again what is already there

Idempotent: data that is there is left alone, and a corpus that is partly filled
is refused rather than mixed (-Force replaces it whole). Everything comes from the
owners' bucket, checked against its .sha256, into ..\tabsira-data. Run
scripts\windows\migrate.ps1 first. A .env whose ENVIRONMENT is production is
refused: the production host uses deploy/load-data.sh.
#>
param(
    [switch]$Check,
    [switch]$NoGeonames,
    [ValidateSet('dump', 'geonames')][string]$GeonamesSource,
    [switch]$Force
)
. "$PSScriptRoot\lib.ps1"
Update-Path
Use-PgBin
Import-DotEnv

$Extensions = @('postgis', 'vector', 'timescaledb', 'pg_trgm', 'unaccent', 'pgcrypto', 'btree_gin', 'btree_gist', 'pg_stat_statements')

if (-not (Test-Path -LiteralPath $EnvFile)) { Fail "No $EnvFile. Run scripts\windows\setup-db.ps1." }
if ($env:ENVIRONMENT -eq 'production') { Fail "ENVIRONMENT in $EnvFile is production: on the production host, run deploy/load-data.sh." }
if (-not (Test-Command psql)) { Fail 'psql is not on PATH. Install PostgreSQL 18 with scripts\windows\install-postgres.ps1.' }
$url = if ($env:SYNC_DATABASE_URL) { $env:SYNC_DATABASE_URL } else { $env:DATABASE_URL }
if (-not $url) { Fail "No DATABASE_URL in $EnvFile." }
$url = $url -replace '\+asyncpg', '' -replace '\+psycopg', ''

function Get-Scalar {
    param([string]$Sql)
    $result = Invoke-Capture 'psql' @($url, '-X', '-q', '-tA', '-v', 'ON_ERROR_STOP=1', '-c', $Sql)
    if ($result.ExitCode -ne 0) { Fail "psql failed: $($result.Output)" }
    return $result.Output.Trim()
}

# A count that is 0 when the table does not exist yet.
function Get-Count {
    param([string]$Table)
    return [long](Get-Scalar "SELECT CASE WHEN to_regclass('$Table') IS NULL THEN 0 ELSE (SELECT count(*) FROM $Table) END")
}

$script:Problems = 0
function Add-Problem {
    param([string]$Message)
    Write-Err $Message
    $script:Problems++
}

# --- The four schemas and the extensions ----------------------------------
Write-Banner 'Schemas and extensions'
[void](Get-Scalar 'SELECT 1')
foreach ($schema in 'app', 'corpus', 'geodata', 'vectors') {
    if ((Get-Scalar "SELECT count(*) FROM pg_namespace WHERE nspname = '$schema'") -eq '1') {
        Write-Ok "schema $schema ($(Get-Scalar "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$schema'") tables)"
    } else {
        Add-Problem "schema $schema is missing: run scripts\windows\migrate.ps1"
    }
}
foreach ($extension in $Extensions) {
    if ((Get-Scalar "SELECT count(*) FROM pg_extension WHERE extname = '$extension'") -ne '1') {
        Add-Problem "extension $extension is missing: run scripts\windows\setup-db.ps1"
    }
}
if ((Get-Scalar "SELECT to_regclass('corpus.quran_verses') IS NOT NULL") -ne 't') {
    Add-Problem 'corpus.quran_verses does not exist: the migrations have not run; run scripts\windows\migrate.ps1'
}
if ($script:Problems -gt 0) { Fail 'The database is not ready for the data (see above).' }
Write-Ok "all $($Extensions.Count) extensions present; the migrations have run"

# --- Load ------------------------------------------------------------------
if (-not $Check) {
    Write-Banner 'GeoNames, corpus, vectors'
    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $RepoRoot 'scripts\data.ps1'))
    if ($Force) { $arguments += '-Force' }
    if ($NoGeonames) {
        $arguments += '-NoGeonames'
    } else {
        $arguments += '-Geonames'
        if ($GeonamesSource) { $arguments += @('-GeonamesSource', $GeonamesSource) }
    }
    # Its own process: data.ps1 ends with `exit`, and its database login stays in it.
    try {
        Invoke-Native (Get-Process -Id $PID).Path $arguments
    } catch {
        Add-Problem "scripts\data.ps1 stopped: $_ (its output above says why)"
    }
}

# --- What is in the database now ---------------------------------------
Write-Banner 'Loaded'
$verses = Get-Count 'corpus.quran_verses'
$hadiths = Get-Count 'corpus.hadiths'
$annotations = Get-Count 'corpus.quran_annotations'
$signals = Get-Count 'corpus.hadith_signals'
$ontology = Get-Count 'corpus.ontology_entities'
$quranVectors = Get-Count 'vectors.quran_verse_embeddings'
$hadithVectors = Get-Count 'vectors.hadith_embeddings'
$places = Get-Count 'geodata.geonames'
$learning = Get-Scalar "SELECT CASE WHEN to_regclass('corpus.learning_path_versions') IS NULL THEN '' ELSE coalesce((SELECT path_version FROM corpus.learning_path_versions WHERE is_active), '') END"
Write-Log "Quran verses          $verses (6236 expected)"
Write-Log "hadiths               $hadiths"
Write-Log "Quran annotations     $annotations"
Write-Log "hadith signals        $signals"
Write-Log "ontology entities     $ontology"
Write-Log "Quran vectors         $quranVectors (all models)"
Write-Log "hadith vectors        $hadithVectors (all models)"
Write-Log "learning path         $(if ($learning) { $learning } else { 'none active' })"
Write-Log "GeoNames places       $places$(if ($NoGeonames) { ' (-NoGeonames)' })"
if ($verses -ne 6236) { Add-Problem "The Quran store holds $verses verses, not 6236." }
if ($hadiths -eq 0) { Add-Problem 'No hadith is stored.' }
if ($annotations -eq 0 -or $signals -eq 0) { Add-Problem 'The annotations or hadith signals are missing.' }
if ($ontology -eq 0) { Add-Problem 'The world ontology is not loaded.' }
if (-not $learning) { Add-Problem 'No learning path version is active.' }
if ($quranVectors -lt $verses -or $hadithVectors -lt $hadiths) { Add-Problem "The vectors do not cover the store: import them (VECTORS_ARCHIVE_URL in $EnvFile)." }
if (-not $NoGeonames -and $places -eq 0) { Add-Problem 'GeoNames is empty.' }
if ($script:Problems -gt 0) { Fail "$($script:Problems) item(s) to fix." }
Write-Ok 'The database holds the data.'
exit 0
