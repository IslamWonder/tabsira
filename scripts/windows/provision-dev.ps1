<#
Provision this Windows machine for TABSIRA, natively: no Docker, no WSL. The
PowerShell counterpart of scripts/provision-dev.sh (Ubuntu).

  1. elevated, in its own window (Windows asks once):
       Node 24 LTS; PostgreSQL 18 with PostGIS, pgvector and TimescaleDB;
       a Redis-compatible server; the hosts file       (provision-system.ps1)
  2. uv, the pinned pnpm, the quality tools            (install-tools.ps1)
  3. role, databases, schemas, extensions, .env        (setup-db.ps1)
  4. nginx for http://tabsira.test, port 80            (setup-nginx-local.ps1)
  5. dependencies and git hooks                        (install.ps1)

Then: scripts\windows\migrate.ps1, and scripts\windows\dev.ps1 to run.
Idempotent: every step starts with the check that says it is already done.
Everything outside the checkout goes to ../tabsira-tools (TABSIRA_TOOLS).

Usage: scripts\windows\provision-dev.ps1 [-SkipSystem] [-SkipInstall] [-SkipVision]
                                         [-PgvectorZip <zip>] [-SkipPgvector] [-SkipNode]
  -SkipSystem    leave out the elevated part (already done)
  -SkipInstall   leave out the dependencies (run install.ps1 later)
  -SkipVision    do not install services/vision's dependencies (about 1 GB)
  -PgvectorZip   a pgvector build for PostgreSQL 18 you trust, instead of
                 building it from source with the Visual Studio build tools
  -SkipPgvector  no pgvector at all (the vectors chain will not migrate)
  -SkipNode      keep the Node that is installed
#>
param(
    [switch]$SkipSystem,
    [switch]$SkipInstall,
    [switch]$SkipVision,
    [string]$PgvectorZip,
    [switch]$SkipPgvector,
    [switch]$SkipNode
)
. "$PSScriptRoot\lib.ps1"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Invoke-Step {
    param([string]$Script, [string[]]$Arguments = @())
    $global:LASTEXITCODE = 0
    & (Join-Path $PSScriptRoot $Script) @Arguments
    if ($LASTEXITCODE) { Fail "$Script failed ($LASTEXITCODE)" }
}

Write-Banner '1/5 System: Node, PostgreSQL, Redis, hosts (elevated)'
if ($SkipSystem) {
    Skip 'system provisioning (-SkipSystem)'
} else {
    $log = Join-Path $LogDir 'provision-system.log'
    $list = @('-PgPassFile', $PgPassFile, '-LogFile', $log)
    if ($PgvectorZip) { $list += @('-PgvectorZip', (Resolve-Path $PgvectorZip).Path) }
    if ($SkipPgvector) { $list += '-SkipPgvector' }
    if ($SkipNode) { $list += '-SkipNode' }
    if (Test-Admin) {
        Invoke-Step 'provision-system.ps1' $list
    } else {
        Write-Log "Windows will ask for elevation; the elevated window logs to $log"
        $code = Invoke-Elevated -Script (Join-Path $PSScriptRoot 'provision-system.ps1') -Arguments $list
        if ($code -ne 0) {
            if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 40 | ForEach-Object { Write-Host "  | $_" } }
            Fail "the elevated part failed ($code); the full log is $log"
        }
        Write-Ok 'System provisioning done'
    }
    Update-Path
}

Write-Banner '2/5 Tools: uv, pnpm, quality tools'
Invoke-Step 'install-tools.ps1'

Write-Banner '3/5 Database'
Invoke-Step 'setup-db.ps1'

Write-Banner '4/5 nginx for tabsira.test'
Invoke-Step 'setup-nginx-local.ps1'

Write-Banner '5/5 Dependencies and git hooks'
if ($SkipInstall) {
    Skip 'dependencies (-SkipInstall)'
} else {
    $list = @()
    if ($SkipVision) { $list += '-SkipVision' }
    Invoke-Step 'install.ps1' $list
}

Write-Ok 'Development machine provisioned.'
Write-Host @"

Next steps:
  1. scripts\windows\migrate.ps1   geodata chain, then app chain, then vectors chain
  2. docs/SETUP.md steps 4 to 7    corpora, scripture store, GeoNames, vectors
  3. scripts\windows\dev.ps1       nginx + api + worker + web (+ vision) with reload
  4. http://tabsira.test  (API: http://api.tabsira.test)
"@
