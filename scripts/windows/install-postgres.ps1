<#
Install PostgreSQL 18 and the extensions TABSIRA needs on Windows, natively,
what scripts/install-postgres.sh does on Ubuntu (DECISIONS.md, decision 15):

  PostgreSQL 18   the EDB installer through winget, unattended, as the Windows
                  service postgresql-x64-18, under ../tabsira-tools/PostgreSQL/18
                  (pgAdmin and StackBuilder left out). The superuser password is
                  generated once and written to the user's pgpass.conf, where
                  psql and every script here read it; it is never printed.
  PostGIS 3.6     the Windows bundle OSGeo publishes for PostgreSQL 18
  TimescaleDB     the zip Timescale publishes for PostgreSQL 18 on Windows
                  (the Community build, with the policies decision 13 needs)
  pgvector        built from its source release with the Visual Studio C++
                  build tools, the way its README says: pgvector publishes no
                  Windows binary. The build tools are installed through winget
                  when missing (about 15 minutes, a few GB). -PgvectorZip takes
                  a build you trust instead; -SkipPgvector leaves it out.
  shared_preload_libraries = timescaledb, pg_stat_statements, then one restart

pg_trgm, unaccent, pgcrypto, btree_gin, btree_gist and pg_stat_statements ship
with the server. An existing PostgreSQL 18 (any location) is used as it is;
then its superuser password must already be in pgpass.conf. Idempotent.
Needs an elevated PowerShell.

Usage: scripts\windows\install-postgres.ps1 [-PgPassFile <path>] [-PgvectorZip <zip>] [-SkipPgvector]
#>
param(
    [string]$PgPassFile,
    [string]$Prefix,
    [string]$DataDir,
    [string]$PgvectorZip,
    [switch]$SkipPgvector
)
if ($PgPassFile) { $env:PGPASSFILE = $PgPassFile }
. "$PSScriptRoot\lib.ps1"

Assert-Admin 'Run scripts\windows\provision-dev.ps1, which asks for elevation itself.'

$PostgisVersion = '3.6.2'
$PostgisUrl = "https://download.osgeo.org/postgis/windows/pg$PgVersion/postgis-bundle-pg$PgVersion-${PostgisVersion}x64.zip"
$TimescaleVersion = '2.30.2'
$TimescaleUrl = "https://github.com/timescale/timescaledb/releases/download/$TimescaleVersion/timescaledb-postgresql-$PgVersion-windows-amd64.zip"
$PgvectorVersion = '0.8.7'
$PgvectorUrl = "https://github.com/pgvector/pgvector/archive/refs/tags/v$PgvectorVersion.zip"
$PreloadRequired = @('timescaledb', 'pg_stat_statements')
$BuildDir = Join-Path $ToolsDir 'build'

function Get-ControlVersion {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match "^default_version\s*=\s*'([^']+)'" } | Select-Object -First 1
    if ($line -match "'([^']+)'") { return $Matches[1] }
    return ''
}

function Wait-ForPostgres {
    param([string]$ServiceName)
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-PsqlAdmin) { return }
        Start-Sleep -Seconds 1
    }
    Fail "PostgreSQL did not answer within 30 seconds as postgres on 127.0.0.1:$PgPort. Is its password in $PgPassFile? (service: $ServiceName)"
}

# Start the service. When it refuses because of a shared_preload_libraries
# value an earlier run left in postgresql.auto.conf (a library that fails to
# load keeps the whole server down), that line is dropped and the start is
# tried once more; the preload step below sets it again.
function Start-PgService {
    param([string]$ServiceName, [string]$DataDir)
    try {
        Start-Service -Name $ServiceName
        return
    } catch {
        $autoConf = Join-Path $DataDir 'postgresql.auto.conf'
        $lines = if (Test-Path -LiteralPath $autoConf) { @(Get-Content -LiteralPath $autoConf) } else { @() }
        $kept = @($lines | Where-Object { $_ -notmatch '^\s*shared_preload_libraries\s*=' })
        if ($kept.Count -eq $lines.Count) { throw }
        Write-Warn "$ServiceName did not start; dropping shared_preload_libraries from $autoConf and trying again (the PostgreSQL log in $DataDir\log says why)"
        Set-Content -LiteralPath $autoConf -Value $kept -Encoding ASCII
        Start-Service -Name $ServiceName
    }
}

# Files the running server holds open (its OpenSSL, a preloaded extension)
# cannot be replaced: the copy happens while the service is stopped.
function Invoke-WithStoppedServer {
    param([string]$ServiceName, [string]$DataDir, [scriptblock]$Action)
    Write-Log "Stopping the service $ServiceName for the copy"
    Stop-Service -Name $ServiceName -Force
    try {
        & $Action
    } finally {
        Write-Log "Starting the service $ServiceName"
        Start-PgService $ServiceName $DataDir
    }
    Wait-ForPostgres $ServiceName
}

# --- 1. The server ---------------------------------------------------------
Write-Banner "PostgreSQL $PgVersion"
$installation = Get-PgInstallation
if ($installation) {
    Write-Ok "PostgreSQL $($installation.Version) is installed at $($installation.BaseDir)"
} else {
    if (-not $Prefix) { $Prefix = Join-Path $ToolsDir "PostgreSQL\$PgVersion" }
    if (-not $DataDir) { $DataDir = Join-Path $Prefix 'data' }
    $password = New-RandomHex 24
    # The installer reads its options from a file, so the password never goes on
    # a command line where any process could read it.
    $optionFile = Join-Path $env:TEMP "tabsira-postgresql-$PID.ini"
    @(
        'mode=unattended'
        'unattendedmodeui=none'
        "superpassword=$password"
        "servicename=$PgServiceName"
        "serverport=$PgPort"
        "prefix=$Prefix"
        "datadir=$DataDir"
        'disable-components=stackbuilder,pgAdmin'
        'install_runtimes=1'
        'create_shortcuts=0'
    ) | Set-Content -LiteralPath $optionFile -Encoding ASCII
    Protect-File $optionFile
    try {
        Write-Log "Installing PostgreSQL $PgVersion under $Prefix (service $PgServiceName, port $PgPort)"
        [void](Install-WingetPackage -Id "PostgreSQL.PostgreSQL.$PgVersion" -Override "--optionfile $optionFile")
    } finally {
        Remove-Item -LiteralPath $optionFile -Force -ErrorAction SilentlyContinue
    }
    Set-PgPassEntry -File $PgPassFile -User 'postgres' -Password $password
    Set-PgPassEntry -File $PgPassFile -HostName 'localhost' -User 'postgres' -Password $password
    Write-Ok "Superuser password written to $PgPassFile"
    $installation = Get-PgInstallation
    if (-not $installation) { Fail "the installer finished but no PostgreSQL $PgVersion is registered under HKLM:\SOFTWARE\PostgreSQL\Installations" }
}
$pgRoot = $installation.BaseDir
$dataDir = $installation.DataDir
$serviceName = $installation.ServiceName
$extensionDir = Join-Path $pgRoot 'share\extension'
$libDir = Join-Path $pgRoot 'lib'
Use-PgBin

$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if (-not $service) { Fail "the service $serviceName does not exist" }
if ($service.Status -ne 'Running') {
    Write-Log "Starting the service $serviceName"
    Start-PgService $serviceName $dataDir
}
Set-Service -Name $serviceName -StartupType Automatic
Wait-ForPostgres $serviceName
Write-Ok "PostgreSQL answers: $(Invoke-Psql -Tuples -Sql 'SHOW server_version')"

# --- 2. PostGIS ------------------------------------------------------------
Write-Banner "PostGIS $PostgisVersion"
$installed = Get-ControlVersion (Join-Path $extensionDir 'postgis.control')
if ($installed -eq $PostgisVersion) {
    Write-Ok "PostGIS $installed is installed"
} else {
    $name = "postgis-bundle-pg$PgVersion-${PostgisVersion}x64.zip"
    $md5 = ((Get-RemoteText "$PostgisUrl.md5") -split '\s+')[0]
    $zip = Get-Download -Url $PostgisUrl -Name $name -Md5 $md5
    $dir = Join-Path $BuildDir 'postgis'
    Expand-ZipTo $zip $dir
    $bundle = Get-ChildItem -LiteralPath $dir -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'bin') } | Select-Object -First 1
    if (-not $bundle) { Fail "no bin folder inside $name" }
    Write-Log "Copying the PostGIS bundle into $pgRoot"
    # The bundle ships OpenSSL, zlib and a few other libraries under the names
    # the server uses; an older copy breaks pgcrypto and the server's TLS. In
    # bin and lib a file the server already has is kept (PostGIS runs on the
    # server's OpenSSL 3 just as well); share holds the bundle's own files.
    Invoke-WithStoppedServer $serviceName $dataDir {
        foreach ($sub in 'bin', 'lib', 'share') {
            $source = Join-Path $bundle.FullName $sub
            if (-not (Test-Path -LiteralPath $source)) { continue }
            $destination = Join-Path $pgRoot $sub
            foreach ($file in Get-ChildItem -LiteralPath $source -Recurse -File) {
                $target = Join-Path $destination $file.FullName.Substring($source.Length + 1)
                if ($sub -ne 'share' -and (Test-Path -LiteralPath $target)) { continue }
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
                Copy-Item -LiteralPath $file.FullName -Destination $target -Force
            }
        }
    }
    Remove-Item -Recurse -Force -LiteralPath $dir
    # ST_Transform needs PROJ's data; the bundle's own installer sets this too.
    $projDir = Get-ChildItem -LiteralPath (Join-Path $pgRoot 'share\contrib') -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'postgis-*' } | ForEach-Object { Join-Path $_.FullName 'proj' } | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($projDir -and -not [Environment]::GetEnvironmentVariable('PROJ_LIB', 'Machine')) {
        [Environment]::SetEnvironmentVariable('PROJ_LIB', $projDir, 'Machine')
        Write-Log "PROJ_LIB set to $projDir (machine)"
    }
    $gdalDir = Join-Path $pgRoot 'gdal-data'
    if ((Test-Path -LiteralPath $gdalDir) -and -not [Environment]::GetEnvironmentVariable('GDAL_DATA', 'Machine')) {
        [Environment]::SetEnvironmentVariable('GDAL_DATA', $gdalDir, 'Machine')
        Write-Log "GDAL_DATA set to $gdalDir (machine)"
    }
    Write-Ok "PostGIS $(Get-ControlVersion (Join-Path $extensionDir 'postgis.control')) copied"
}

# --- 2b. The server's own libraries ----------------------------------------
# An earlier copy of the bundle may have replaced the server's OpenSSL; then
# pgcrypto (built against the server's own) does not load. Every library of the
# server that differs from the official binaries of the same build is put back.
Write-Banner 'Server libraries'
function Test-LibraryLoads {
    param([string]$Library)
    try { [void](Invoke-Psql -Sql "LOAD '$Library'"); return $true } catch { return $false }
}
if (Test-LibraryLoads 'pgcrypto') {
    Write-Ok "pgcrypto loads: the server's libraries are its own"
} else {
    $build = $installation.Version
    $zip = Get-Download -Url "https://get.enterprisedb.com/postgresql/postgresql-$build-windows-x64-binaries.zip" -Name "postgresql-$build-windows-x64-binaries.zip"
    $restoreDir = Join-Path $BuildDir 'restore'
    if (Test-Path -LiteralPath $restoreDir) { Remove-Item -Recurse -Force -LiteralPath $restoreDir }
    New-Item -ItemType Directory -Force -Path $restoreDir | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
    $restore = @()
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName -notmatch '^pgsql/(bin|lib)/[^/]+\.(dll|exe)$') { continue }
            $target = Join-Path $pgRoot ($entry.FullName.Substring(6) -replace '/', '\')
            if (-not (Test-Path -LiteralPath $target)) { continue }
            $extracted = Join-Path $restoreDir $entry.Name
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $extracted, $true)
            if ((Get-FileHash -LiteralPath $extracted).Hash -ne (Get-FileHash -LiteralPath $target).Hash) {
                $restore += [pscustomobject]@{ Source = $extracted; Target = $target }
            }
        }
    } finally {
        $archive.Dispose()
    }
    if ($restore.Count -eq 0) { Fail "pgcrypto does not load, yet no library differs from the official build $build; the PostgreSQL log in $dataDir\log says more" }
    Write-Log "Restoring $($restore.Count) libraries of build ${build}: $(($restore | ForEach-Object { Split-Path -Leaf $_.Target }) -join ', ')"
    Invoke-WithStoppedServer $serviceName $dataDir {
        foreach ($item in $restore) { Copy-Item -LiteralPath $item.Source -Destination $item.Target -Force }
    }
    Remove-Item -Recurse -Force -LiteralPath $restoreDir
    if (-not (Test-LibraryLoads 'pgcrypto')) { Fail 'pgcrypto still does not load after restoring the server libraries' }
    Write-Ok "Server libraries restored; pgcrypto loads"
}

# --- 3. TimescaleDB ------------------------------------------------------
Write-Banner "TimescaleDB $TimescaleVersion"
$installed = Get-ControlVersion (Join-Path $extensionDir 'timescaledb.control')
if ($installed -eq $TimescaleVersion) {
    Write-Ok "TimescaleDB $installed is installed"
} else {
    $zip = Get-Download -Url $TimescaleUrl -Name "timescaledb-$TimescaleVersion-postgresql-$PgVersion-windows-amd64.zip"
    $dir = Join-Path $BuildDir 'timescaledb'
    Expand-ZipTo $zip $dir
    $files = Get-ChildItem -LiteralPath $dir -Recurse -File
    $dlls = @($files | Where-Object { $_.Extension -eq '.dll' })
    $extension = @($files | Where-Object { $_.Extension -in '.control', '.sql' })
    if ($dlls.Count -eq 0 -or $extension.Count -eq 0) { Fail "the TimescaleDB zip holds no dll or control file" }
    Write-Log "Copying $($dlls.Count) libraries and $($extension.Count) extension files into $pgRoot"
    Invoke-WithStoppedServer $serviceName $dataDir {
        $dlls | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $libDir -Force }
        $extension | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $extensionDir -Force }
    }
    Remove-Item -Recurse -Force -LiteralPath $dir
    Write-Ok "TimescaleDB $(Get-ControlVersion (Join-Path $extensionDir 'timescaledb.control')) copied"
}

# --- 4. pgvector -----------------------------------------------------------
Write-Banner "pgvector $PgvectorVersion"
function Find-VcVars {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) { return $null }
    $result = Invoke-Capture $vswhere @('-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath')
    if ($result.ExitCode -ne 0 -or -not $result.Output) { return $null }
    $vcvars = Join-Path $result.Output.Trim() 'VC\Auxiliary\Build\vcvars64.bat'
    if (Test-Path -LiteralPath $vcvars) { return $vcvars }
    return $null
}

$installed = Get-ControlVersion (Join-Path $extensionDir 'vector.control')
if ($installed) {
    Write-Ok "pgvector $installed is installed"
} elseif ($PgvectorZip) {
    Write-Log "Installing pgvector from $PgvectorZip"
    $dir = Join-Path $BuildDir 'pgvector-zip'
    Expand-ZipTo (Resolve-Path $PgvectorZip).Path $dir
    $files = Get-ChildItem -LiteralPath $dir -Recurse -File
    $dlls = @($files | Where-Object { $_.Name -like 'vector*.dll' })
    $extension = @($files | Where-Object { $_.Name -like 'vector*' -and $_.Extension -in '.control', '.sql' })
    if ($dlls.Count -eq 0 -or $extension.Count -eq 0) { Fail "$PgvectorZip holds no vector dll or control file" }
    $dlls | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $libDir -Force }
    $extension | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $extensionDir -Force }
    Remove-Item -Recurse -Force -LiteralPath $dir
    Write-Ok "pgvector $(Get-ControlVersion (Join-Path $extensionDir 'vector.control')) copied"
} elseif ($SkipPgvector) {
    Skip 'pgvector (-SkipPgvector); the vectors chain and semantic search will not work'
} else {
    $vcvars = Find-VcVars
    if (-not $vcvars) {
        Write-Log 'The Visual Studio C++ build tools are missing; installing them (this takes a while)'
        $buildTools = Join-Path $ToolsDir 'BuildTools'
        [void](Install-WingetPackage -Id 'Microsoft.VisualStudio.2022.BuildTools' -Override "--quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --installPath $buildTools")
        $vcvars = Find-VcVars
        if (-not $vcvars) { Fail 'the C++ build tools are still missing after the install (vcvars64.bat not found). Install the "Desktop development with C++" workload, or pass -PgvectorZip.' }
    }
    $zip = Get-Download -Url $PgvectorUrl -Name "pgvector-$PgvectorVersion.zip"
    $dir = Join-Path $BuildDir 'pgvector'
    Expand-ZipTo $zip $dir
    $source = Get-ChildItem -LiteralPath $dir -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'Makefile.win') } | Select-Object -First 1
    if (-not $source) { Fail 'no Makefile.win inside the pgvector source zip' }
    # A batch file, because the quoting of `cmd /c` cannot carry both a quoted
    # vcvars path and a quoted PGROOT.
    $batch = Join-Path $source.FullName 'tabsira-build.cmd'
    @(
        '@echo off'
        "call `"$vcvars`" || exit /b 1"
        "set `"PGROOT=$pgRoot`""
        'nmake /F Makefile.win || exit /b 1'
        'nmake /F Makefile.win install || exit /b 1'
    ) | Set-Content -LiteralPath $batch -Encoding ASCII
    Write-Log "Building pgvector against $pgRoot"
    Invoke-Native 'cmd.exe' @('/d', '/c', $batch) -WorkingDirectory $source.FullName
    Remove-Item -Recurse -Force -LiteralPath $dir
    $installed = Get-ControlVersion (Join-Path $extensionDir 'vector.control')
    if (-not $installed) { Fail 'the pgvector build finished but share\extension\vector.control is missing' }
    Write-Ok "pgvector $installed built and installed"
}

# --- 5. Preloaded libraries ------------------------------------------------
Write-Banner 'shared_preload_libraries'
# The server shows the list as "a, b"; compare libraries, not spacing.
function ConvertTo-LibraryList {
    param([string]$Value)
    $list = @()
    foreach ($lib in ($Value -split ',')) {
        $lib = $lib.Trim(" '`"")
        if ($lib -and ($list -notcontains $lib)) { $list += $lib }
    }
    return , $list
}
$current = Invoke-Psql -Tuples -Sql 'SHOW shared_preload_libraries'
$final = ConvertTo-LibraryList $current
foreach ($required in $PreloadRequired) {
    if ($final -contains $required) { continue }
    # timescaledb asks to be loaded first.
    if ($required -eq 'timescaledb') { $final = @($required) + $final } else { $final += $required }
}
$joined = $final -join ','
if ($joined -eq ((ConvertTo-LibraryList $current) -join ',')) {
    Write-Ok "shared_preload_libraries already holds $($PreloadRequired -join ', ') ($current)"
} else {
    Write-Log "shared_preload_libraries: '$current' -> '$joined'"
    # ALTER SYSTEM writes postgresql.auto.conf, which wins over postgresql.conf.
    # A list parameter takes one literal per library: a single 'a,b' literal
    # would be stored as one library named "a,b", and the server would not start.
    $literals = ($final | ForEach-Object { "'$_'" }) -join ', '
    [void](Invoke-Psql -Sql "ALTER SYSTEM SET shared_preload_libraries = $literals")
    Write-Log "Restarting the service $serviceName"
    Stop-Service -Name $serviceName -Force
    Start-PgService $serviceName $dataDir
    Wait-ForPostgres $serviceName
    $effective = Invoke-Psql -Tuples -Sql 'SHOW shared_preload_libraries'
    if (((ConvertTo-LibraryList $effective) -join ',') -ne $joined) { Fail "shared_preload_libraries is '$effective' after the restart, not '$joined'" }
    Write-Ok "shared_preload_libraries is now $effective"
}

# --- 6. Every extension must be installable --------------------------------
$missing = @()
foreach ($ext in 'postgis', 'pg_trgm', 'unaccent', 'pgcrypto', 'btree_gin', 'btree_gist', 'pg_stat_statements', 'vector', 'timescaledb') {
    if ((Invoke-Psql -Tuples -Sql "SELECT count(*) FROM pg_available_extensions WHERE name = '$ext'") -ne '1') { $missing += $ext }
}
if ($missing.Count -gt 0) { Fail "these extensions are not available on this server: $($missing -join ' ')" }

Write-Ok "PostgreSQL $PgVersion is ready: $(Invoke-Psql -Tuples -Sql "SELECT string_agg(name || ' ' || default_version, ', ' ORDER BY name) FROM pg_available_extensions WHERE name IN ('postgis','vector','timescaledb','pg_stat_statements')")"
Write-Log 'Next: scripts\windows\setup-db.ps1 creates the role, databases, schemas and extensions.'
exit 0
