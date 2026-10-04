<#
Run the API, the scan worker, the web app and (when present) the vision
service behind http://tabsira.test, the way `make dev` (scripts/dev.sh) does,
from PowerShell. nginx (scripts\windows\setup-nginx-local.ps1) is started
first when it is not running yet, and stopped at the end when this script
started it.

  nginx    ../tabsira-tools/nginx          80 -> the apps below
  api      uv run uvicorn in apps/api      127.0.0.1:8000 (API_HOST, API_PORT)
  worker   the scan jobs, from Redis
  web      next dev in apps/web            127.0.0.1:3000
  vision   uv run uvicorn in services/vision   127.0.0.1:8100 (VISION_HOST, VISION_PORT)

Every line of output is prefixed with the service name. When one service
stops, the others are stopped too, so a crash is never left half-running.
Ctrl-C stops everything. A service whose app does not exist yet is skipped.
The full output of each service is also in ../tabsira-tools/logs/<name>.log.

Usage: scripts\windows\dev.ps1 [-NoVision] [-NoWorker] [-NoNginx] [-WebPort 3000]
       scripts\windows\dev.ps1 -Stop      stop a dev.ps1 running in another window
#>
param(
    [switch]$NoVision,
    [switch]$NoWorker,
    [switch]$NoNginx,
    [int]$WebPort = 3000,
    [switch]$Stop
)
. "$PSScriptRoot\lib.ps1"
Update-Path
Set-NodeEnvironment
Set-PythonEnvironment
Set-Location -LiteralPath $RepoRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Another window asks this one to stop by creating this file.
$stopFile = Join-Path $LogDir 'dev.stop'
if ($Stop) {
    Write-Utf8File -Path $stopFile -Content "$(Get-Date -Format o)`n"
    Write-Log 'asked the running dev.ps1 to stop'
    exit 0
}
Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $EnvFile)) { Write-Warn '.env is missing: run scripts\windows\setup-db.ps1 (or provision-dev.ps1)' }
$missingHosts = Get-MissingLocalHosts
if ($missingHosts.Count -gt 0) { Write-Warn "$($missingHosts -join ', ') not in the hosts file: run scripts\windows\provision-dev.ps1" }
Import-DotEnv
if (-not (Test-TcpPort -Port ([int]$PgPort))) { Write-Warn "nothing answers on 127.0.0.1:$PgPort (PostgreSQL): the API will not start" }
if (-not (Test-TcpPort -Port 6379)) { Write-Warn 'nothing answers on 127.0.0.1:6379 (Redis): scans will fail' }

$apiHost = if ($env:API_HOST) { $env:API_HOST } else { '127.0.0.1' }
$apiPort = if ($env:API_PORT) { $env:API_PORT } else { '8000' }
$visionHost = if ($env:VISION_HOST) { $env:VISION_HOST } else { '127.0.0.1' }
$visionPort = if ($env:VISION_PORT) { $env:VISION_PORT } else { '8100' }

$services = New-Object System.Collections.ArrayList
$colors = @{ nginx = 'DarkGray'; api = 'Green'; worker = 'Magenta'; web = 'Cyan'; vision = 'Yellow' }

function Start-DevService {
    param([string]$Name, [string]$File, [string[]]$Arguments, [string]$WorkingDirectory)
    $log = Join-Path $LogDir "$Name.log"
    $errorLog = Join-Path $LogDir "$Name.err.log"
    foreach ($f in $log, $errorLog) { if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force } }
    Write-Log "starting $Name"
    $process = Start-Process -FilePath $File -ArgumentList (ConvertTo-ArgumentString $Arguments) -WorkingDirectory $WorkingDirectory `
        -NoNewWindow -PassThru -RedirectStandardOutput $log -RedirectStandardError $errorLog
    # Without this, ExitCode stays empty once the process has ended.
    $null = $process.Handle
    [void]$services.Add([pscustomobject]@{
            Name    = $Name
            Process = $process
            Readers = @(
                [pscustomobject]@{ Path = $log; Position = 0L },
                [pscustomobject]@{ Path = $errorLog; Position = 0L }
            )
        })
}

# Print what a service wrote since the last look, one prefixed line at a time.
function Write-NewOutput {
    param($Service)
    foreach ($reader in $Service.Readers) {
        if (-not (Test-Path -LiteralPath $reader.Path)) { continue }
        $stream = $null
        try {
            $stream = New-Object System.IO.FileStream($reader.Path, 'Open', 'Read', 'ReadWrite')
            if ($stream.Length -le $reader.Position) { continue }
            $stream.Position = $reader.Position
            $buffer = New-Object byte[] ($stream.Length - $reader.Position)
            $read = $stream.Read($buffer, 0, $buffer.Length)
            $text = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $read)
            # Keep an unfinished line for the next look.
            $cut = $text.LastIndexOf("`n")
            if ($cut -lt 0) { continue }
            $reader.Position += [System.Text.Encoding]::UTF8.GetByteCount($text.Substring(0, $cut + 1))
            foreach ($line in $text.Substring(0, $cut).Split("`n")) {
                Write-Host "[$($Service.Name)] " -NoNewline -ForegroundColor $colors[$Service.Name]
                Write-Host $line.TrimEnd("`r")
            }
        } catch {
            # The file is being written; try again on the next look.
        } finally {
            if ($stream) { $stream.Dispose() }
        }
    }
}

function Stop-DevService {
    param($Service)
    if ($Service.Process.HasExited) { return }
    # The whole tree: uv and pnpm start the real server as a child process.
    $null = Invoke-Capture 'taskkill.exe' @('/PID', "$($Service.Process.Id)", '/T', '/F')
}

$nginxDir = Join-Path $ToolsDir 'nginx'
$nginxExe = Join-Path $nginxDir 'nginx.exe'
$nginxStartedHere = $false

try {
    # --- nginx ---------------------------------------------------------------
    if ($NoNginx) {
        Skip 'nginx (-NoNginx)'
    } elseif (-not (Test-Path -LiteralPath $nginxExe)) {
        Write-Warn "nginx is not set up ($nginxExe): run scripts\windows\setup-nginx-local.ps1; the apps answer on their own ports meanwhile"
    } elseif (Get-Process -Name 'nginx' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $nginxExe }) {
        Write-Ok 'nginx is already running'
    } else {
        Write-Log 'starting nginx'
        Start-Process -FilePath $nginxExe -ArgumentList (ConvertTo-ArgumentString @('-p', $nginxDir, '-c', 'conf\tabsira.conf')) -WorkingDirectory $nginxDir -WindowStyle Hidden
        $nginxStartedHere = $true
        Start-Sleep -Milliseconds 800
        if (-not (Test-TcpPort -Port 80)) { Write-Warn "nginx did not open port 80: see $(Join-Path $LogDir 'nginx.error.log')" }
    }

    # --- The apps --------------------------------------------------------------
    $uv = (Get-Command uv -ErrorAction SilentlyContinue)
    $apiDir = Join-Path $RepoRoot 'apps\api'
    if ((Test-Path -LiteralPath (Join-Path $apiDir 'pyproject.toml')) -and $uv) {
        # Fail with a readable message before uvicorn would bury it in a traceback.
        Write-Log 'Checking the API configuration...'
        Invoke-Native 'uv' @('run', 'python', '-m', 'src.cli.check_config') -WorkingDirectory $apiDir
        Start-DevService -Name 'api' -File $uv.Source -WorkingDirectory $apiDir `
            -Arguments @('run', 'uvicorn', 'src.main:app', '--reload', '--reload-dir', 'src', '--host', $apiHost, '--port', $apiPort)
        if ($NoWorker) { Skip 'worker (-NoWorker)' }
        else { Start-DevService -Name 'worker' -File $uv.Source -WorkingDirectory $apiDir -Arguments @('run', 'python', '-m', 'src.cli.scan_worker') }
    } else {
        Skip 'api and worker: apps/api/pyproject.toml or uv is missing'
    }

    $webDir = Join-Path $RepoRoot 'apps\web'
    if (Test-Path -LiteralPath (Join-Path $webDir 'package.json')) {
        $pnpm = Get-Command 'pnpm.cmd' -ErrorAction SilentlyContinue
        if (-not $pnpm) { throw 'pnpm is missing. Run: scripts\windows\install.ps1' }
        # The dev script of package.json, with its port: next dev --hostname 127.0.0.1.
        Start-DevService -Name 'web' -File $pnpm.Source -WorkingDirectory $webDir `
            -Arguments @('exec', 'next', 'dev', '--hostname', '127.0.0.1', '--port', "$WebPort")
    } else {
        Skip 'web: apps/web does not exist yet'
    }

    $visionDir = Join-Path $RepoRoot 'services\vision'
    if ($NoVision) {
        Skip 'vision (-NoVision)'
    } elseif ((Test-Path -LiteralPath (Join-Path $visionDir 'pyproject.toml')) -and $uv) {
        if (-not (Test-Path -LiteralPath (Join-Path $visionDir 'weights'))) { Write-Warn 'no weights yet: run services/vision/scripts/fetch-weights.sh (Git bash) or uv run python -m vision.weights in services/vision' }
        Start-DevService -Name 'vision' -File $uv.Source -WorkingDirectory $visionDir `
            -Arguments @('run', 'uvicorn', 'vision.main:create_app', '--factory', '--reload', '--host', $visionHost, '--port', $visionPort)
    } else {
        Skip 'vision: services/vision does not exist yet'
    }

    if ($services.Count -eq 0) { throw 'nothing to run: no app exists yet' }
    $names = ($services | ForEach-Object { $_.Name }) -join ', '
    Write-Log "running: $names. Web http://tabsira.test, API http://api.tabsira.test. Ctrl-C stops all."

    # Ctrl-C arrives here as a key, so the shutdown below always runs.
    if (-not [Console]::IsInputRedirected) { [Console]::TreatControlCAsInput = $true }
    $stopped = $null
    while (-not $stopped) {
        foreach ($service in $services) { Write-NewOutput $service }
        foreach ($service in $services) {
            if ($service.Process.HasExited) { $stopped = "$($service.Name) stopped (exit $($service.Process.ExitCode))"; break }
        }
        if (-not [Console]::IsInputRedirected -and [Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq 'C' -and ($key.Modifiers -band [ConsoleModifiers]::Control)) { $stopped = 'Ctrl-C' }
        }
        if (Test-Path -LiteralPath $stopFile) { $stopped = 'dev.ps1 -Stop' }
        if (-not $stopped) { Start-Sleep -Milliseconds 250 }
    }
    if ($stopped -in 'Ctrl-C', 'dev.ps1 -Stop') { Write-Log "${stopped}: stopping everything" } else { Write-Err "${stopped}; stopping the rest" }
} finally {
    if (-not [Console]::IsInputRedirected) { [Console]::TreatControlCAsInput = $false }
    foreach ($service in $services) { Stop-DevService $service }
    Start-Sleep -Milliseconds 300
    foreach ($service in $services) { Write-NewOutput $service }
    if ($nginxStartedHere) {
        $null = Invoke-Capture $nginxExe @('-s', 'quit', '-p', $nginxDir, '-c', 'conf\tabsira.conf')
    }
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
    Write-Log 'stopped'
}
