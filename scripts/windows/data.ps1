<#
Load the reference data into the database, once: what `make data`
(scripts/data.sh) and scripts/seed-geonames.sh do, from PowerShell.

  geodata     GeoNames into the geodata schema: a pg_restore of the owners' export
              (-GeodataDump, or the newest geodata/*.dump of the bucket, 336 MB),
              or with -FromGeoNames scripts/seed-geonames.sh (about 600 MB from
              geonames.org into data/cache/geonames, then millions of rows)
  scripture   the Quran, the hadiths, the annotations and the signals
              (src.cli.import_scripture). The two corpora come from the bucket's
              corpus/ when data/corpus lacks them, and whatever the bucket holds
              under cache/ fills data/cache first: a source file that changed
              upstream since the owners' import is then read from their copy. The
              importer still checks every file against its source's own manifest.
  ontology    the world ontology (src.cli.import_ontology)
  masar       the learning path, every data/masar/*.json (src.cli.import_masar)
  vectors     the published vector archive (930 MB, checked against its .sha256),
              imported by scripts/vectors/import.sh; then embed_corpus, which finds
              nothing left to compute

Each step looks at the database first and does nothing when its data is there,
so running the script again by mistake costs a few queries. -Force imports again
anyway. A step that fails does not stop the steps that do not depend on it; the
vectors need the scripture store. The exit code is 1 when a step failed.

The bucket is the owners' public one (docs/SETUP.md, "what to fetch");
-BucketUrl names another. Its files are kept beside the checkout, in
../tabsira-data, except the corpora (data/corpus) and the cache (data/cache).

Usage: scripts\windows\data.ps1 [-Only geodata,scripture,ontology,masar,vectors]
                                [-Force] [-GeodataDump <file.dump>]
                                [-FromGeoNames [-GeonamesLimit <N>]] [-BucketUrl <url>]

Reads DATABASE_URL and the other settings from the root .env. Run
scripts\windows\migrate.ps1 first. The GeoNames import and the vector import run
the repository's shell scripts with Git's bash, which Git for Windows installs.
#>
param(
    [ValidateSet('geodata', 'scripture', 'ontology', 'masar', 'vectors')]
    [string[]]$Only = @('geodata', 'scripture', 'ontology', 'masar', 'vectors'),
    [switch]$Force,
    [string]$GeodataDump,
    [switch]$FromGeoNames,
    [int]$GeonamesLimit = 0,
    [string]$BucketUrl = 'https://s3-v2.riastorage.com/tabsira'
)
. "$PSScriptRoot\lib.ps1"
Update-Path
Use-GitBash
Set-PythonEnvironment
Use-PgBin
Import-DotEnv

if (-not $env:DATABASE_URL) { Fail 'DATABASE_URL is not set. Run scripts\windows\setup-db.ps1, which writes it into the root .env.' }
foreach ($tool in 'uv', 'psql') {
    if (-not (Test-Command $tool)) { Fail "$tool is not installed. Run scripts\windows\install.ps1." }
}
$apiDir = Join-Path $RepoRoot 'apps\api'
# psql does not understand SQLAlchemy's driver suffix.
$psqlUrl = if ($env:SYNC_DATABASE_URL) { $env:SYNC_DATABASE_URL } else { $env:DATABASE_URL }
$psqlUrl = $psqlUrl -replace '\+asyncpg', '' -replace '\+psycopg', ''

function Get-Scalar {
    param([string]$Sql)
    $result = Invoke-Capture 'psql' @($psqlUrl, '-X', '-q', '-tA', '-v', 'ON_ERROR_STOP=1', '-c', $Sql)
    if ($result.ExitCode -ne 0) { throw "psql failed: $($result.Output)" }
    return $result.Output.Trim()
}

function Test-Table {
    param([string]$Name)
    return ((Get-Scalar "SELECT to_regclass('$Name') IS NOT NULL") -eq 't')
}

function Invoke-Api {
    param([string[]]$Arguments)
    Invoke-Native 'uv' (@('run', '--quiet', 'python', '-m') + $Arguments) -WorkingDirectory $apiDir | Out-Host
}

# Git's bash, never the WSL launcher in System32.
function Get-GitBash {
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $git) { Fail 'git is not installed: the GeoNames and vector imports run with Git bash.' }
    $bash = Join-Path (Split-Path -Parent (Split-Path -Parent $git.Source)) 'bin\bash.exe'
    if (-not (Test-Path -LiteralPath $bash)) { Fail "Git bash not found at $bash" }
    return $bash
}

# A path as Git bash reads it: forward slashes, the drive letter kept.
function ConvertTo-BashPath { param([string]$Path) return ($Path -replace '\\', '/') }

function Invoke-Bash {
    param([string]$Script, [string[]]$Arguments = @())
    $env:DATABASE_URL = $psqlUrl
    try {
        Invoke-Native (Get-GitBash) (@((ConvertTo-BashPath $Script)) + $Arguments) -WorkingDirectory $RepoRoot | Out-Host
    } finally {
        Import-DotEnv
    }
}

# --- The owners' bucket ----------------------------------------------------

$DataDir = Join-Path (Split-Path -Parent $RepoRoot) 'tabsira-data'

# Every object under a prefix, with its size: the bucket's listing is public.
function Get-BucketObjects {
    param([string]$Prefix)
    $objects = @()
    $token = $null
    do {
        $url = "$($BucketUrl)?list-type=2&prefix=$([Uri]::EscapeDataString($Prefix))"
        if ($token) { $url += "&continuation-token=$([Uri]::EscapeDataString($token))" }
        [xml]$listing = Get-RemoteText $url
        foreach ($item in @($listing.ListBucketResult.Contents)) {
            if ($item) { $objects += [pscustomobject]@{ Key = $item.Key; Size = [long]$item.Size } }
        }
        $token = if ($listing.ListBucketResult.IsTruncated -eq 'true') { $listing.ListBucketResult.NextContinuationToken } else { $null }
    } while ($token)
    return $objects
}

# One object to a local file, unless a file of the same size is there already.
# The callers check the content: a SHA-256 file, or the importer's own manifests.
function Save-BucketObject {
    param([pscustomobject]$Object, [string]$Destination)
    if ((Test-Path -LiteralPath $Destination) -and (Get-Item -LiteralPath $Destination).Length -eq $Object.Size) { return }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Write-Log "Downloading $($Object.Key) ($([math]::Ceiling($Object.Size / 1MB)) MB)..."
    Invoke-Native 'curl.exe' @('-fL', '--retry', '3', '-sS', '-o', "$Destination.part", "$BucketUrl/$($Object.Key)") | Out-Host
    Move-Item -Force -LiteralPath "$Destination.part" -Destination $Destination
}

function Test-Sha256File {
    param([string]$File, [string]$SumFile)
    $expected = ((Get-Content -LiteralPath $SumFile -Raw).Trim() -split '\s+')[0]
    return ((Get-FileHash -Algorithm SHA256 -LiteralPath $File).Hash -eq $expected.ToUpper())
}

# --- The steps -----------------------------------------------------------

function Step-Geodata {
    if (-not (Test-Table 'geodata.geonames')) { throw 'geodata.geonames is missing: run scripts\windows\migrate.ps1' }
    $places = [long](Get-Scalar 'SELECT count(*) FROM geodata.geonames')
    if ($places -gt 0 -and -not $Force) {
        Write-Ok "GeoNames already imported ($places places): nothing to do. Use -Force to import again."
        return 'skipped'
    }
    $dump = $GeodataDump
    if (-not $dump -and -not $FromGeoNames) {
        # The newest export of the bucket: the names carry their date.
        $object = @(Get-BucketObjects 'geodata/' | Where-Object { $_.Key -like '*.dump' } | Sort-Object Key) | Select-Object -Last 1
        if ($object) {
            $dump = Join-Path $DataDir ('geodata\' + (Split-Path -Leaf $object.Key))
            Save-BucketObject $object $dump
            $sum = @(Get-BucketObjects "$($object.Key).sha256") | Select-Object -First 1
            if ($sum) { Save-BucketObject $sum "$dump.sha256" }
        } else {
            Write-Warn 'no GeoNames export in the bucket: importing from geonames.org instead'
        }
    }
    if ($dump) {
        if (-not (Test-Path -LiteralPath $dump)) { throw "$dump does not exist" }
        if (Test-Path -LiteralPath "$dump.sha256") {
            if (-not (Test-Sha256File $dump "$dump.sha256")) { throw "$dump does not match its .sha256: delete it and run again" }
            Write-Ok 'The GeoNames export matches its .sha256'
        } else {
            Write-Warn "no $dump.sha256 beside the export: it is restored unchecked"
        }
        $user = ([Uri]($psqlUrl -replace '^postgresql:', 'http:')).UserInfo.Split(':')[0]
        Write-Log 'Restoring the GeoNames export (geodata schema only)...'
        Invoke-Native 'pg_restore' @('--no-owner', "--role=$user", '--clean', '--if-exists', '--schema=geodata', '-d', $psqlUrl, $dump) | Out-Host
    } else {
        $arguments = @()
        if ($GeonamesLimit -gt 0) { $arguments += @('--limit', "$GeonamesLimit") }
        if ($Force) { $arguments += '--force' }
        # The extracted files are named inside the SQL that psql.exe runs: a Git bash
        # path (/tmp/...) means nothing to it, a drive path with forward slashes does.
        $env:GEONAMES_TMP_DIR = ConvertTo-BashPath $env:TEMP
        Invoke-Bash (Join-Path $RepoRoot 'scripts\seed-geonames.sh') $arguments
    }
    Write-Ok "GeoNames: $(Get-Scalar 'SELECT count(*) FROM geodata.geonames') places"
    return 'done'
}

function Test-ScriptureStored {
    if (-not (Test-Table 'app.quran_verses')) { return $false }
    $stored = Get-Scalar @'
SELECT (SELECT count(*) FROM app.quran_verses) = 6236
   AND (SELECT count(*) FROM app.hadiths) > 0
   AND (SELECT count(*) FROM app.quran_annotations) > 0
   AND (SELECT count(*) FROM app.hadith_signals) > 0
'@
    return ($stored -eq 't')
}

function Step-Scripture {
    if (-not (Test-Table 'app.quran_verses')) { throw 'app.quran_verses is missing: run scripts\windows\migrate.ps1' }
    if ((Test-ScriptureStored) -and -not $Force) {
        Write-Ok 'Scripture store already imported: nothing to do. Use -Force to import again.'
        return 'skipped'
    }
    $corpusDir = if ($env:CORPUS_DIR) { $env:CORPUS_DIR } else { Join-Path $RepoRoot 'data\corpus' }
    $corpusFiles = 'quran-annotations.json', 'sunnah-enriched.json', 'SHA256SUMS'
    if (@($corpusFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $corpusDir $_)) }).Count -gt 0) {
        foreach ($object in Get-BucketObjects 'corpus/') {
            $name = Split-Path -Leaf $object.Key
            if ($corpusFiles -contains $name -and -not (Test-Path -LiteralPath (Join-Path $corpusDir $name))) {
                Save-BucketObject $object (Join-Path $corpusDir $name)
            }
        }
    }
    # The owners' copies of the downloads (data/cache): a file its source changed since
    # their import is read from here. A failing listing leaves the importer to download.
    try {
        foreach ($object in Get-BucketObjects 'cache/') {
            if ($object.Key.EndsWith('/')) { continue }
            Save-BucketObject $object (Join-Path $RepoRoot ('data\' + ($object.Key -replace '/', '\')))
        }
    } catch {
        Write-Warn "the bucket's cache/ could not be read ($_): the importer downloads from the sources"
    }
    foreach ($name in 'quran-annotations.json', 'sunnah-enriched.json') {
        if (-not (Test-Path -LiteralPath (Join-Path $corpusDir $name))) {
            throw "$corpusDir\$name is missing. Copy it there (docs/ASSET_MANIFEST.md names its source and SHA-256)."
        }
    }
    # The corpora are checked against SHA256SUMS when it is there, as docs/SETUP.md step 4 does.
    $sums = Join-Path $corpusDir 'SHA256SUMS'
    if (Test-Path -LiteralPath $sums) {
        foreach ($line in Get-Content -LiteralPath $sums) {
            if ($line -notmatch '^([0-9a-fA-F]{64})\s+\*?(.+)$') { continue }
            $file = Join-Path $corpusDir $Matches[2].Trim()
            if ((Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash -ne $Matches[1].ToUpper()) {
                throw "$file does not match SHA256SUMS (a copy with Windows line endings does not: it must be byte for byte)"
            }
        }
        Write-Ok 'The two corpora match SHA256SUMS'
    }
    Invoke-Api @('src.cli.import_scripture', 'download', 'quran', 'annotations', 'hadith', 'signals',
        '--cache-dir', (Join-Path $RepoRoot 'data\cache'), '--corpus-dir', $corpusDir)
    return 'done'
}

# Either default search model covering every verse and every hadith means the archive is in.
function Test-VectorsCovered {
    $covered = Get-Scalar @'
SELECT count(*) FROM (
    SELECT model FROM vectors.quran_verse_embeddings
    WHERE model IN ('text-embedding-3-large', 'bge-m3') GROUP BY model
    HAVING count(*) >= (SELECT count(*) FROM app.quran_verses)
    INTERSECT
    SELECT model FROM vectors.hadith_embeddings
    WHERE model IN ('text-embedding-3-large', 'bge-m3') GROUP BY model
    HAVING count(*) >= (SELECT count(*) FROM app.hadiths)
) full_models
'@
    return ($covered -ne '0')
}

function Get-VectorFolder {
    if ($env:VECTORS_ARCHIVE) {
        if (Test-Path -LiteralPath $env:VECTORS_ARCHIVE -PathType Container) { return $env:VECTORS_ARCHIVE }
        if (-not (Test-Path -LiteralPath $env:VECTORS_ARCHIVE -PathType Leaf)) { throw "VECTORS_ARCHIVE=$($env:VECTORS_ARCHIVE) is neither an archive nor a folder" }
        $archive = $env:VECTORS_ARCHIVE
    } else {
        $url = if ($env:VECTORS_ARCHIVE_URL) { $env:VECTORS_ARCHIVE_URL } else { 'https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz' }
        $dir = if ($env:VECTORS_DIR) { $env:VECTORS_DIR } else { Join-Path (Split-Path -Parent $RepoRoot) 'tabsira-data\vectors' }
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $archive = Join-Path $dir ([IO.Path]::GetFileName(([Uri]$url).AbsolutePath))
        $sumFile = "$archive.sha256"
        $verified = $false
        if ((Test-Path -LiteralPath $archive) -and (Test-Path -LiteralPath $sumFile)) {
            $expected = ((Get-Content -LiteralPath $sumFile -Raw).Trim() -split '\s+')[0]
            $verified = ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash -eq $expected.ToUpper())
        }
        if ($verified) {
            Write-Log "Archive already downloaded and verified: $archive"
        } else {
            Write-Log "Downloading the scripture vectors (about 930 MB) from $url ..."
            Invoke-Native 'curl.exe' @('-fL', '--retry', '3', '-o', $sumFile, "$url.sha256") | Out-Host
            # -C - resumes an interrupted download.
            Invoke-Native 'curl.exe' @('-fL', '--retry', '3', '-C', '-', '-o', $archive, $url) | Out-Host
            $expected = ((Get-Content -LiteralPath $sumFile -Raw).Trim() -split '\s+')[0]
            if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash -ne $expected.ToUpper()) {
                throw "$archive does not match its .sha256: delete it and run again"
            }
            Write-Ok 'Archive verified against its .sha256'
        }
    }
    $folder = Join-Path (Split-Path -Parent $archive) ([IO.Path]::GetFileName($archive) -replace '\.tar\.gz$', '')
    if (-not (Test-Path -LiteralPath (Join-Path $folder 'SHA256SUMS'))) {
        Write-Log "Extracting $archive ..."
        # Windows' own tar (bsdtar): Git's tar reads C: in a path as a remote host.
        Invoke-Native (Join-Path $env:SystemRoot 'System32\tar.exe') @('-xzf', $archive, '-C', (Split-Path -Parent $archive)) | Out-Host
    }
    if (-not (Test-Path -LiteralPath (Join-Path $folder 'SHA256SUMS'))) { throw "$folder is not an extracted vector archive" }
    return $folder
}

function Step-Vectors {
    foreach ($table in 'vectors.quran_verse_embeddings', 'vectors.hadith_embeddings') {
        if (-not (Test-Table $table)) { throw "$table is missing: run scripts\windows\migrate.ps1" }
    }
    if (-not (Test-ScriptureStored)) { throw 'the scripture store is not imported: the vectors are matched to its rows' }
    if ((Test-VectorsCovered) -and -not $Force) {
        Write-Ok 'Scripture vectors are already in the database: nothing to import. Use -Force to import again.'
        return 'skipped'
    }
    $folder = Get-VectorFolder
    # The repository's import, never the archive's own copy (it may predate the vectors schema).
    Invoke-Bash (Join-Path $RepoRoot 'scripts\vectors\import.sh') @((ConvertTo-BashPath $folder))
    # Only with the archive in: embed_corpus would otherwise pay for what the archive holds (docs/EMBEDDINGS.md).
    if (Test-VectorsCovered) {
        Invoke-Api @('src.cli.embed_corpus')
    } else {
        Write-Warn 'the archive did not cover the store; embed_corpus not run (it would compute the vectors, which costs money)'
    }
    return 'done'
}

function Step-Ontology {
    if (-not (Test-Table 'app.ontology_entities')) { throw 'app.ontology_entities is missing: run scripts\windows\migrate.ps1' }
    $entities = [long](Get-Scalar 'SELECT count(*) FROM app.ontology_entities')
    if ($entities -gt 0 -and -not $Force) {
        Write-Ok "World ontology already imported ($entities entities): nothing to do. Use -Force to import again."
        return 'skipped'
    }
    Invoke-Api @('src.cli.import_ontology')
    Write-Ok "World ontology: $(Get-Scalar 'SELECT count(*) FROM app.ontology_entities') entities"
    return 'done'
}

# What the first release of the learning path must hold (docs/LEARNING_PATH.md), as in data-learning.sh.
$MasarFirstVersion = 'tabsira-masar-1.0'
$MasarFirstDomains = 16
$MasarFirstUnits = 96

function Step-Masar {
    if (-not (Test-Table 'app.learning_path_versions')) { throw 'app.learning_path_versions is missing: run scripts\windows\migrate.ps1' }
    $masarDir = Join-Path $RepoRoot 'data\masar'
    # Version order, numeric: 1.0, then 1.1, then 1.10.
    $files = @(Get-ChildItem -LiteralPath $masarDir -Filter '*.json' | Sort-Object {
            $v = $_.BaseName -replace '^.*-', ''
            try { [version]$v } catch { [version]'0.0' }
        })
    $pending = @($files | Where-Object {
            $Force -or (Get-Scalar "SELECT count(*) FROM app.learning_path_versions WHERE path_version = '$($_.BaseName)'") -eq '0'
        })
    if ($pending.Count -eq 0) {
        Write-Ok 'Learning path already imported: nothing to do. Use -Force to import again.'
        return 'skipped'
    }
    Write-Log 'Checking that the learning path data is current...'
    Invoke-Api @('src.cli.parse_masar', '--check', '--expect-domains', "$MasarFirstDomains", '--expect-units', "$MasarFirstUnits")
    foreach ($file in $pending) {
        $arguments = @('src.cli.import_masar', '--source', $file.FullName)
        if ($file.BaseName -eq $MasarFirstVersion) {
            $arguments += @('--expect-domains', "$MasarFirstDomains", '--expect-units', "$MasarFirstUnits")
        }
        Write-Log "Importing $($file.Name)..."
        Invoke-Api $arguments
    }
    return 'done'
}

# --- Run -------------------------------------------------------------------

$steps = [ordered]@{
    geodata   = { Step-Geodata }
    scripture = { Step-Scripture }
    # Before the vectors, as data.sh: they ship in the repository and load in seconds,
    # so a download or an API key problem there never leaves the database without them.
    ontology  = { Step-Ontology }
    masar     = { Step-Masar }
    vectors   = { Step-Vectors }
}
$results = [ordered]@{}
foreach ($name in $steps.Keys) {
    if ($Only -notcontains $name) { continue }
    Write-Banner $name
    $started = Get-Date
    try {
        $outcome = & $steps[$name]
        $results[$name] = "$outcome in $([int]((Get-Date) - $started).TotalSeconds) s"
    } catch {
        Write-Err "$name failed: $_"
        $results[$name] = "FAILED: $_"
    }
}

Write-Banner 'Summary'
foreach ($name in $results.Keys) { Write-Host ('  {0,-10} {1}' -f $name, $results[$name]) }
if (@($results.Values | Where-Object { $_ -like 'FAILED*' }).Count -gt 0) { exit 1 }
Write-Ok 'Reference data loaded'
exit 0
