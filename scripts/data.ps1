<#
Install the reference data on a native Windows machine: what `make data`
(scripts/data.sh) does, step for step. The two files change together (AGENTS.md).

Usage (from the checkout, after scripts\windows\migrate.ps1):
  powershell -ExecutionPolicy Bypass -File scripts\data.ps1 [-Force] [-Geonames | -NoGeonames] [-GeonamesSource dump|geonames]

In this order, each step once only (it skips what is there; -Force, or
DATA_FORCE=true in .env, installs everything again):

  GeoNames   the verified dump from the owners' bucket (GEONAMES_SOURCE=dump, the
             default). Only when GEODATA_DUMP or GEODATA_DUMP_URL is set,
             GEONAMES_SOURCE is geonames, or -Geonames / -GeonamesSource is given;
             -NoGeonames skips it always. The geonames source (a fresh import from
             geonames.org) needs scripts/seed-geonames.sh, which has no Windows
             counterpart: use the dump, or run scripts/data.sh in WSL.
  corpus     the scripture store, the world ontology and the learning path, from the
             verified archive (CORPUS_ARCHIVE, CORPUS_ARCHIVE_URL; docs/CORPUS.md).
             Building the store from its sources is in scripts/data.sh only.
  standard   the leak guard's skeletons of the Quran in today's spelling, derived from
             the stored text (src.cli.import_scripture standard, task 05.9): written
             where missing or stale, nothing otherwise, every time.
  vectors    the published archive (VECTORS_ARCHIVE, VECTORS_ARCHIVE_URL;
             docs/EMBEDDINGS.md), then src.cli.embed_corpus for what is missing.

It reads the root .env, like data.sh. The database login goes into the PG*
variables of this process only: the password is never printed and never on a
command line. The checks run the same SQL files as the shell scripts
(scripts/corpus/*.sql from the archive, scripts/geodata/restore-*.sql,
scripts/vectors/import.sql).

Needs: psql and pg_restore (PostgreSQL 18 client, scripts\windows\install-postgres.ps1),
curl.exe and tar.exe (part of Windows 10 1803 and later), uv (winget install
astral-sh.uv). SHA-256 is checked with Get-FileHash.
#>
param(
    [switch]$Force,
    [switch]$Geonames,
    [switch]$NoGeonames,
    [ValidateSet('dump', 'geonames')][string]$GeonamesSource
)
. "$PSScriptRoot\windows\lib.ps1"
Update-Path
Set-PythonEnvironment
Use-PgBin
Import-DotEnv

$DataRoot = Join-Path (Split-Path -Parent $RepoRoot) 'tabsira-data'
$CorpusTables = @(
    'quran_surahs', 'quran_verses', 'quran_verse_history', 'quran_verse_search', 'quran_annotations',
    'hadith_collections', 'hadiths', 'hadith_search', 'hadith_signals',
    'ontology_entities', 'learning_path_versions', 'learning_domains', 'learning_units'
)
# Tables an archive may or may not hold (scripts/corpus/import.sh): the derived skeletons
# of task 05.9 came after the archive of 2026-10-04; the standard step writes them.
$OptionalCorpusTables = @('quran_verse_standard_guard')
$GeodataTables = @('geonames', 'geonames_alternate_names', 'geonames_hierarchy', 'geonames_country_info', 'geonames_postal_codes')
$DefaultCorpusUrl = 'https://s3-v2.riastorage.com/tabsira/corpus/tabsira-corpus-2026-10-04.tar.gz'
$DefaultGeodataUrl = 'https://s3-v2.riastorage.com/tabsira/geodata/tabsira-geodata-2026-10-04.dump'
$DefaultVectorsUrl = 'https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz'
if ($env:DATA_FORCE -eq 'true') { $Force = $true }

# --- Tools ------------------------------------------------------------------
$tools = [ordered]@{
    'psql'       = 'Install PostgreSQL 18 with scripts\windows\install-postgres.ps1; its bin folder holds psql.'
    'pg_restore' = 'Install PostgreSQL 18 with scripts\windows\install-postgres.ps1; its bin folder holds pg_restore.'
    'curl.exe'   = 'It is part of Windows 10 1803 and later (C:\Windows\System32\curl.exe).'
    'tar.exe'    = 'It is part of Windows 10 1803 and later (C:\Windows\System32\tar.exe).'
    'uv'         = 'Install it with: winget install --id astral-sh.uv'
}
foreach ($tool in $tools.Keys) {
    if (-not (Test-Command $tool)) { Fail "$tool is not on PATH. $($tools[$tool])" }
}

# --- The database, in PG* variables ------------------------------------------
$url = if ($env:SYNC_DATABASE_URL) { $env:SYNC_DATABASE_URL } else { $env:DATABASE_URL }
if (-not $url) { Fail 'DATABASE_URL is not set. Run scripts\windows\setup-db.ps1, then scripts\windows\migrate.ps1.' }
if ($url -notmatch '^postgresql(\+[a-z]+)?://([^:@/]+)(:([^@]*))?@([^:/?]+)(:(\d+))?/([^?]+)') {
    Fail 'DATABASE_URL is not of the form postgresql://user:password@host:port/database.'
}
$env:PGUSER = [uri]::UnescapeDataString($Matches[2])
$env:PGPASSWORD = if ($Matches[4]) { [uri]::UnescapeDataString($Matches[4]) } else { '' }
$env:PGHOST = $Matches[5]
$env:PGPORT = if ($Matches[7]) { $Matches[7] } else { '5432' }
$env:PGDATABASE = $Matches[8]
$env:PGCLIENTENCODING = 'UTF8'
$env:PGCONNECT_TIMEOUT = '5'

function Invoke-Query {
    param([string]$Sql)
    $result = Invoke-Capture 'psql' @('-X', '-q', '-tA', '-v', 'ON_ERROR_STOP=1', '-c', $Sql)
    if ($result.ExitCode -ne 0) { Fail "psql failed: $($result.Output)" }
    return $result.Output
}

# Run SQL files in one psql session, in order (a transaction may span them).
function Invoke-SqlFiles {
    param([string[]]$Files)
    $list = @('-X', '-q', '-v', 'ON_ERROR_STOP=1', '-o', 'NUL')
    foreach ($file in $Files) { $list += @('-f', $file) }
    Invoke-Native 'psql' $list
}

function Assert-Table {
    param([string]$Table)
    if ((Invoke-Query "SELECT to_regclass('$Table') IS NOT NULL") -ne 't') {
        Fail "$Table is missing: run scripts\windows\migrate.ps1 first."
    }
}

# A path psql's \i reads on Windows: forward slashes, in single quotes.
function ConvertTo-PsqlPath { param([string]$Path) return "'" + ($Path -replace '\\', '/') + "'" }

# --- SHA-256 ---------------------------------------------------------------
function Get-Sha256 { param([string]$Path) return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLower() }

# True when FILE.sha256 is beside FILE and names its hash.
function Test-Sha256File {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath "$Path.sha256")) { return $false }
    $expected = ((Get-Content -LiteralPath "$Path.sha256" -Raw).Trim() -split '\s+')[0].ToLower()
    return $expected -eq (Get-Sha256 $Path)
}

# Every file named in DIR\SHA256SUMS matches it.
function Assert-Sha256Sums {
    param([string]$Dir)
    foreach ($line in Get-Content -LiteralPath (Join-Path $Dir 'SHA256SUMS')) {
        if (-not $line.Trim()) { continue }
        $expected, $name = $line.Trim() -split '\s+\*?', 2
        if ((Get-Sha256 (Join-Path $Dir $name)) -ne $expected.ToLower()) {
            Fail "$name does not match SHA256SUMS in ${Dir}: download the archive again."
        }
    }
}

# Download URL into DIR once, with its .sha256, and check it; return the file.
function Get-VerifiedDownload {
    param([string]$Url, [string]$Dir, [string]$What)
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    $file = Join-Path $Dir ([IO.Path]::GetFileName(([uri]$Url).AbsolutePath))
    if ((Test-Path -LiteralPath $file) -and (Test-Sha256File $file)) {
        Write-Log "Already downloaded and verified: $file"
        return $file
    }
    Write-Log "Downloading $What from $Url ..."
    Invoke-Native 'curl.exe' @('-fL', '--retry', '3', '-o', "$file.sha256", "$Url.sha256")
    Invoke-Native 'curl.exe' @('-fL', '--retry', '3', '-o', $file, $Url)
    if (-not (Test-Sha256File $file)) { Fail "$file does not match its .sha256: delete it and run again." }
    Write-Ok "$What verified against its .sha256"
    return $file
}

# A local FILE, checked against FILE.sha256 when there is one.
function Assert-LocalFile {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path -LiteralPath $Path)) { Fail "$Key=$Path does not exist." }
    if (Test-Path -LiteralPath "$Path.sha256") {
        if (-not (Test-Sha256File $Path)) { Fail "$Path does not match its .sha256." }
        Write-Ok "$Path verified against its .sha256"
    } else {
        Write-Warn "No .sha256 beside ${Path}: its contents are checked by the import only."
    }
}

# Extract an archive next to itself and return the folder (tabsira-x-<date>).
function Expand-DataArchive {
    param([string]$Archive)
    $dir = Split-Path -Parent $Archive
    $folder = Join-Path $dir ([IO.Path]::GetFileName($Archive) -replace '\.tar\.gz$', '')
    if (Test-Path -LiteralPath $folder) { Remove-Item -Recurse -Force -LiteralPath $folder }
    Invoke-Native 'tar.exe' @('-xzf', $Archive, '-C', $dir)
    return $folder
}

# The value of an archive URL key: set, else empty in .env ("never download"), else the default.
function Get-ArchiveUrl {
    param([string]$Key, [string]$Default)
    $value = [Environment]::GetEnvironmentVariable($Key, 'Process')
    if ($value) { return $value }
    if ((Test-Path -LiteralPath $EnvFile) -and (Select-String -LiteralPath $EnvFile -Pattern "^$Key=" -Quiet)) { return '' }
    return $Default
}

# pg_restore's list of the data of TABLES (parents first), of the OPTIONAL tables the dump
# holds, and the sequences of SCHEMA.
function Write-RestoreList {
    param([string]$Dump, [string]$Schema, [string[]]$Tables, [string]$ListFile, [string[]]$Optional = @())
    $toc = Invoke-Capture 'pg_restore' @('-l', $Dump)
    if ($toc.ExitCode -ne 0) { Fail "$Dump is not a pg_dump archive." }
    $list = @()
    foreach ($table in $Tables) {
        $entry = @($toc.Lines | Where-Object { $_ -match "^\d+; \d+ \d+ TABLE DATA $Schema $table( |$)" })
        if ($entry.Count -eq 0) { Fail "$Dump holds no data for $Schema.$table." }
        $list += $entry
    }
    foreach ($table in $Optional) {
        $list += @($toc.Lines | Where-Object { $_ -match "^\d+; \d+ \d+ TABLE DATA $Schema $table( |$)" })
    }
    $list += @($toc.Lines | Where-Object { $_ -match "^\d+; \d+ \d+ SEQUENCE SET $Schema " })
    Write-Utf8File -Path $ListFile -Content (($list -join "`n") + "`n")
    return @($toc.Lines | Where-Object { $_ -match "^\d+; \d+ \d+ TABLE DATA $Schema " }).Count
}

$WorkDir = Join-Path ([IO.Path]::GetTempPath()) ("tabsira-data-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

try {
    # --- GeoNames ---------------------------------------------------------------
    $source = if ($GeonamesSource) { $GeonamesSource } elseif ($env:GEONAMES_SOURCE) { $env:GEONAMES_SOURCE } else { 'dump' }
    if ($source -notin @('dump', 'geonames')) { Fail "unknown GeoNames source '$source': dump or geonames" }
    $runGeonames = if ($NoGeonames) { $false }
    elseif ($Geonames -or $GeonamesSource) { $true }
    else { [bool]($env:GEODATA_DUMP -or $env:GEODATA_DUMP_URL -or $env:GEONAMES_SOURCE -eq 'geonames') }

    if ($runGeonames) {
        Write-Banner 'GeoNames'
        Assert-Table 'geodata.geonames'
        $places = Invoke-Query 'SELECT count(*) FROM geodata.geonames'
        if ($places -ne '0' -and -not $Force) {
            Write-Ok "GeoNames already imported ($places places): nothing to do. Use -Force to import again."
        } elseif ($source -eq 'geonames') {
            Fail ('The geonames source is scripts/seed-geonames.sh (unzip, awk and sort over about 600 MB), ' +
                'which has no Windows counterpart. Use -GeonamesSource dump, or run ' +
                '"bash scripts/data.sh --geonames-source=geonames" in WSL.')
        } else {
            if ($env:GEODATA_DUMP) {
                $dump = $env:GEODATA_DUMP
                Assert-LocalFile $dump 'GEODATA_DUMP'
            } else {
                $geodataUrl = if ($env:GEODATA_DUMP_URL) { $env:GEODATA_DUMP_URL } else { $DefaultGeodataUrl }
                $geodataDir = if ($env:GEODATA_DIR) { $env:GEODATA_DIR } else { Join-Path $DataRoot 'geodata' }
                $dump = Get-VerifiedDownload $geodataUrl $geodataDir 'GeoNames (about 340 MB)'
            }
            $listFile = Join-Path $WorkDir 'geodata.list'
            $dataFile = Join-Path $WorkDir 'geodata.sql'
            [void](Write-RestoreList $dump 'geodata' $GeodataTables $listFile)
            Invoke-Native 'pg_restore' @('--data-only', '-L', $listFile, '-f', $dataFile, $dump)
            $started = Get-Date
            Write-Log 'Restoring GeoNames (one transaction; the indexes are built again at the end) ...'
            Invoke-SqlFiles @((Join-Path $RepoRoot 'scripts\geodata\restore-begin.sql'), $dataFile,
                (Join-Path $RepoRoot 'scripts\geodata\restore-end.sql'))
            foreach ($table in $GeodataTables) { [void](Invoke-Query "ANALYZE geodata.$table") }
            $places = Invoke-Query 'SELECT count(*) FROM geodata.geonames'
            if ($places -eq '0') { Fail 'The restore left geodata.geonames empty.' }
            Write-Ok "GeoNames installed from the dump in $([int]((Get-Date) - $started).TotalSeconds) s ($places places)."
        }
    } else {
        Write-Log 'GeoNames skipped: set GEODATA_DUMP_URL, or pass -Geonames, to install the places of the atlas.'
    }

    # --- The corpus: scripture store, ontology, learning path ---------------------
    Write-Banner 'Corpus (scripture store, world ontology, learning path)'
    $corpusUrl = Get-ArchiveUrl 'CORPUS_ARCHIVE_URL' $DefaultCorpusUrl
    if (-not $env:CORPUS_ARCHIVE -and -not $corpusUrl) {
        Fail ('No corpus archive (CORPUS_ARCHIVE and CORPUS_ARCHIVE_URL are empty). Building the store from its ' +
            'sources is done by scripts/data.sh only: set CORPUS_ARCHIVE_URL, or run it in WSL.')
    }
    Assert-Table 'corpus.quran_verses'
    $installed = Invoke-Query ("SELECT (SELECT count(*) FROM corpus.quran_verses) = 6236 " +
        "AND EXISTS (SELECT 1 FROM corpus.hadiths) AND EXISTS (SELECT 1 FROM corpus.quran_annotations) " +
        "AND EXISTS (SELECT 1 FROM corpus.hadith_signals) AND EXISTS (SELECT 1 FROM corpus.ontology_entities) " +
        "AND EXISTS (SELECT 1 FROM corpus.learning_path_versions WHERE is_active)")
    if ($installed -eq 't' -and -not $Force) {
        Write-Ok 'The corpus is already installed: nothing to do. Use -Force to install it again.'
    } else {
        if ($env:CORPUS_ARCHIVE) {
            $archive = $env:CORPUS_ARCHIVE
            if (-not (Test-Path -LiteralPath $archive -PathType Container)) { Assert-LocalFile $archive 'CORPUS_ARCHIVE' }
        } else {
            $corpusDir = if ($env:CORPUS_ARCHIVE_DIR) { $env:CORPUS_ARCHIVE_DIR } else { Join-Path $DataRoot 'corpus' }
            $archive = Get-VerifiedDownload $corpusUrl $corpusDir 'the corpus (about 50 MB)'
        }
        $folder = if (Test-Path -LiteralPath $archive -PathType Container) { $archive } else { Expand-DataArchive $archive }

        # What scripts/corpus/import.sh does, with the archive's own SQL files.
        foreach ($name in 'SHA256SUMS', 'corpus.dump', 'manifest.json', 'state.sql', 'verify.sql', 'force-guard.sql') {
            if (-not (Test-Path -LiteralPath (Join-Path $folder $name))) { Fail "$folder is not an extracted corpus archive." }
        }
        Write-Log 'Checking the files against SHA256SUMS'
        Assert-Sha256Sums $folder
        $dumpFile = Join-Path $folder 'corpus.dump'
        $manifestText = Get-Content -LiteralPath (Join-Path $folder 'manifest.json') -Raw -Encoding UTF8
        if (-not $manifestText.Contains("`"sha256`": `"$(Get-Sha256 $dumpFile)`"")) { Fail 'corpus.dump is not the dump the manifest names.' }
        $manifest = $manifestText | ConvertFrom-Json
        $archiveTables = @($manifest.tables.PSObject.Properties.Name)
        $databaseTables = @((Invoke-Query "SELECT tablename FROM pg_tables WHERE schemaname = 'corpus'") -split "`n")
        $absent = @($archiveTables | Where-Object { $databaseTables -notcontains $_ })
        if ($absent.Count -gt 0) { Fail "the database has no corpus table for: $($absent -join ' ') (run migrate.ps1; is this archive older than the schema?)" }
        foreach ($table in $CorpusTables) {
            if ($archiveTables -notcontains $table) { Fail "the archive has no ${table}: it predates this script." }
        }

        $verses = Invoke-Query 'SELECT count(*) FROM corpus.quran_verses'
        $held = Invoke-Query ('SELECT ' + (($CorpusTables | ForEach-Object { "(SELECT count(*) FROM corpus.$_)" }) -join ' + '))
        if (-not $Force) {
            if ($verses -ne '0') { Fail "corpus.quran_verses already holds $verses verses: nothing imported. Use -Force to replace the whole corpus." }
            if ($held -ne '0') { Fail "the corpus is not empty ($held rows): nothing imported. Use -Force to replace the whole corpus." }
        }

        $listFile = Join-Path $WorkDir 'corpus.list'
        $dataFile = Join-Path $WorkDir 'corpus.sql'
        $entries = Write-RestoreList $dumpFile 'corpus' $CorpusTables $listFile $OptionalCorpusTables
        $known = $CorpusTables.Count + @($OptionalCorpusTables | Where-Object { $archiveTables -contains $_ }).Count
        if ($entries -ne $known) { Fail "corpus.dump holds data for $entries tables, this script knows $known of them: use a newer checkout." }
        Invoke-Native 'pg_restore' @('--data-only', '-L', $listFile, '-f', $dataFile, $dumpFile)

        $begin = @('BEGIN;', "SET LOCAL tabsira.scripture_write = 'import';")
        if ($Force) {
            $begin += "\i $(ConvertTo-PsqlPath (Join-Path $folder 'force-guard.sql'))"
            foreach ($table in $OptionalCorpusTables) {
                $begin += "DO `$`$ BEGIN IF to_regclass('corpus.$table') IS NOT NULL THEN DELETE FROM corpus.$table; END IF; END `$`$;"
            }
            for ($index = $CorpusTables.Count - 1; $index -ge 0; $index--) { $begin += "DELETE FROM corpus.$($CorpusTables[$index]);" }
        }
        $beginFile = Join-Path $WorkDir 'corpus-begin.sql'
        Write-Utf8File -Path $beginFile -Content (($begin -join "`n") + "`n")
        $endFile = Join-Path $WorkDir 'corpus-end.sql'
        Write-Utf8File -Path $endFile -Content (
            "SELECT set_config('tabsira.corpus_manifest', `$manifest`$$manifestText`$manifest`$, true);`n" +
            "\i $(ConvertTo-PsqlPath (Join-Path $folder 'verify.sql'))`n" +
            "DO `$`$ BEGIN IF to_regclass('corpus.quran_verse_standard_spans') IS NOT NULL THEN " +
            "REFRESH MATERIALIZED VIEW corpus.quran_verse_standard_spans; END IF; END `$`$;`nCOMMIT;`n")

        Write-Log 'Restoring (one transaction; a failed check leaves the database as it was)'
        Invoke-SqlFiles @($beginFile, $dataFile, $endFile)
        Write-Ok 'Every verse and hadith matches its stored hash; every table matches the manifest.'
        foreach ($table in $CorpusTables) {
            [void](Invoke-Query "ANALYZE corpus.$table")
            Write-Log ('{0,-24} {1}' -f $table, (Invoke-Query "SELECT count(*) FROM corpus.$table"))
        }
    }

    # --- The Quran in today's spelling, for the leak guard (derived skeletons) ------
    # Written where missing or stale, nothing otherwise; a few seconds, so every time.
    Write-Banner "The Quran in today's spelling, for the leak guard (derived skeletons)"
    Invoke-Native 'uv' @('run', '--quiet', 'python', '-m', 'src.cli.import_scripture', 'standard') -WorkingDirectory (Join-Path $RepoRoot 'apps\api')

    # --- Scripture vectors --------------------------------------------------------
    Write-Banner 'Scripture vectors'
    Assert-Table 'vectors.quran_verse_embeddings'
    $defaultModels = "'text-embedding-3-large', 'bge-m3'"
    $covered = Invoke-Query ("SELECT count(*) FROM (SELECT model FROM vectors.quran_verse_embeddings " +
        "WHERE model IN ($defaultModels) GROUP BY model HAVING count(*) >= (SELECT count(*) FROM corpus.quran_verses) " +
        "INTERSECT SELECT model FROM vectors.hadith_embeddings WHERE model IN ($defaultModels) GROUP BY model " +
        "HAVING count(*) >= (SELECT count(*) FROM corpus.hadiths)) full_models")
    $vectorsUrl = Get-ArchiveUrl 'VECTORS_ARCHIVE_URL' $DefaultVectorsUrl
    if ($covered -ne '0' -and -not $Force) {
        Write-Ok 'Scripture vectors are already in the database: nothing to import. Use -Force to import again.'
    } elseif (-not $env:VECTORS_ARCHIVE -and -not $vectorsUrl) {
        Write-Warn 'No vector archive (VECTORS_ARCHIVE and VECTORS_ARCHIVE_URL empty): embed_corpus will compute the vectors, which costs money.'
    } else {
        if ($env:VECTORS_ARCHIVE) {
            $archive = $env:VECTORS_ARCHIVE
            if (-not (Test-Path -LiteralPath $archive -PathType Container)) { Assert-LocalFile $archive 'VECTORS_ARCHIVE' }
        } else {
            $vectorsDir = if ($env:VECTORS_DIR) { $env:VECTORS_DIR } else { Join-Path $DataRoot 'vectors' }
            $archive = Get-VerifiedDownload $vectorsUrl $vectorsDir 'the scripture vectors (about 930 MB)'
        }
        $folder = if (Test-Path -LiteralPath $archive -PathType Container) { $archive } else { Expand-DataArchive $archive }
        Assert-Sha256Sums $folder
        Write-Log 'Importing the vectors (a few minutes) ...'
        # The repository's SQL, never the archive's copy; it reads the .tsv files of the folder.
        Push-Location -LiteralPath $folder
        try {
            Invoke-Native 'psql' @('-X', '-q', '-v', 'ON_ERROR_STOP=1', '-f', (Join-Path $RepoRoot 'scripts\vectors\import.sql'))
        } finally {
            Pop-Location
        }
    }
    Invoke-Native 'uv' @('run', '--quiet', 'python', '-m', 'src.cli.embed_corpus') -WorkingDirectory (Join-Path $RepoRoot 'apps\api')
    Write-Ok 'Scripture vectors checked'
} finally {
    Remove-Item -Recurse -Force -LiteralPath $WorkDir -ErrorAction SilentlyContinue
}
