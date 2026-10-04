<#
The part of the Windows provisioning that needs an elevated PowerShell. It is
started by scripts\windows\provision-dev.ps1 in its own window (UAC) and
writes everything it prints to ../tabsira-tools/logs/provision-system.log:

  1. Node 24 LTS (.nvmrc) through winget; another Node from the same
     installer is replaced
  2. PostgreSQL 18 with PostGIS, pgvector, TimescaleDB   (install-postgres.ps1)
  3. Redis-compatible server on 127.0.0.1:6379            (install-redis.ps1)
  4. tabsira.test, api.tabsira.test, admin.tabsira.test in the hosts file

Everything that can run as the user (uv, mkcert, nginx, the databases, the
dependencies) stays in provision-dev.ps1. Idempotent.

Usage: scripts\windows\provision-system.ps1 -PgPassFile <path> [-PgvectorZip <zip>] [-SkipPgvector] [-SkipNode]
#>
param(
    [string]$PgPassFile,
    [string]$PgvectorZip,
    [switch]$SkipPgvector,
    [switch]$SkipNode,
    [string]$LogFile
)
if ($PgPassFile) { $env:PGPASSFILE = $PgPassFile }
. "$PSScriptRoot\lib.ps1"
Assert-Admin

if (-not $LogFile) { $LogFile = Join-Path $LogDir 'provision-system.log' }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogFile) | Out-Null
Start-Transcript -LiteralPath $LogFile -Append | Out-Null
$exitCode = 0
try {
    Write-Banner '1/4 Node 24 LTS'
    if ($SkipNode) {
        Skip 'Node (-SkipNode)'
    } else {
        $major = Get-NodeMajor
        if ($major -eq 24) {
            Write-Ok "node $((Invoke-Capture 'node' @('--version')).Output)"
        } else {
            if ($major -gt 0) { Write-Log "node is v$major, .nvmrc asks for 24" }
            # The Node MSI refuses to go backwards, so the other version goes first.
            foreach ($id in 'OpenJS.NodeJS', 'OpenJS.NodeJS.LTS') {
                if (Test-WingetPackage $id) {
                    Write-Log "Removing $id"
                    Invoke-Native 'winget' @('uninstall', '--id', $id, '--exact', '--silent', '--accept-source-agreements', '--disable-interactivity')
                }
            }
            [void](Install-WingetPackage -Id 'OpenJS.NodeJS.LTS')
            Update-Path
            $major = Get-NodeMajor
            if ($major -ne 24) { throw "node is v$major after the install, not 24 (OpenJS.NodeJS.LTS is no longer Node 24: install Node 24 yourself and run again with -SkipNode)" }
            Write-Ok "node $((Invoke-Capture 'node' @('--version')).Output)"
        }
    }

    Write-Banner '2/4 PostgreSQL and its extensions'
    $list = @()
    if ($PgvectorZip) { $list += @('-PgvectorZip', $PgvectorZip) }
    if ($SkipPgvector) { $list += '-SkipPgvector' }
    $global:LASTEXITCODE = 0
    & "$PSScriptRoot\install-postgres.ps1" @list
    if ($LASTEXITCODE) { throw "install-postgres.ps1 failed ($LASTEXITCODE)" }

    Write-Banner '3/4 Redis'
    $global:LASTEXITCODE = 0
    & "$PSScriptRoot\install-redis.ps1"
    if ($LASTEXITCODE) { throw "install-redis.ps1 failed ($LASTEXITCODE)" }

    Write-Banner '4/4 hosts file'
    $missing = Get-MissingLocalHosts
    if ($missing.Count -eq 0) {
        Write-Ok "$($LocalHosts -join ', ') are in $HostsFile"
    } else {
        $line = "127.0.0.1 $($missing -join ' ')"
        Write-Log "Adding to ${HostsFile}: $line"
        # Appended, so the rest of the file is kept byte for byte.
        $content = Get-Content -LiteralPath $HostsFile -Raw
        if ($content -and -not $content.EndsWith("`n")) { Add-Content -LiteralPath $HostsFile -Value '' -Encoding ASCII }
        Add-Content -LiteralPath $HostsFile -Value $line -Encoding ASCII
        Write-Ok 'hosts file updated'
    }
    Write-Ok 'System provisioning done.'
} catch {
    Write-Err "$_"
    Write-Err ($_.ScriptStackTrace)
    $exitCode = 1
} finally {
    Stop-Transcript | Out-Null
}
exit $exitCode
