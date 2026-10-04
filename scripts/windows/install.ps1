<#
Install every dependency: web (pnpm workspace), api and vision (uv), git
hooks. What `make install` (scripts/install.sh) does, from PowerShell. Apps
that do not exist yet are skipped. In CI the lock files are authoritative: an
out-of-date one fails the install instead of being rewritten.

Usage: scripts\windows\install.ps1 [-SkipVision]
  -SkipVision   leave out services/vision (its CPU torch is about 1 GB)
#>
param([switch]$SkipVision)
. "$PSScriptRoot\lib.ps1"
Update-Path
Set-NodeEnvironment
Set-PythonEnvironment
Set-Location -LiteralPath $RepoRoot

Write-Banner 'Prerequisites'
if (-not (Test-Command node)) { Fail 'Node 24 is required (see .nvmrc). Run: scripts\windows\provision-dev.ps1' }
$major = Get-NodeMajor
if ($major -lt 24) { Fail "Node 24 or newer is required, found $((Invoke-Capture 'node' @('--version')).Output) (see .nvmrc)." }
if (-not (Test-Command uv)) { Fail 'uv is required: scripts\windows\install-tools.ps1' }
Set-PnpmVersion
if (-not (Test-Command pnpm)) { Fail 'pnpm is required: npm install -g pnpm (the version is pinned in package.json)' }
if (-not (Test-Command bash)) { Fail "Git's bash is required for the git hooks and pnpm's prepare script" }
Write-Ok "node $((Invoke-Capture 'node' @('--version')).Output), pnpm $((Invoke-Capture 'pnpm' @('--version')).Output), $((Invoke-Capture 'uv' @('--version')).Output)"

Write-Banner 'Node workspace (pnpm)'
if (Test-Ci) { Invoke-Native 'pnpm' @('install', '--frozen-lockfile') } else { Invoke-Native 'pnpm' @('install') }

# uv downloads the Python the apps need (pyproject: 3.12). On Windows its last
# step, the minor-version link, has failed once with the install itself
# complete; the syncs below only need `uv python find` to answer.
Write-Banner 'Python 3.12 (uv)'
$result = Invoke-Capture 'uv' @('python', 'install', '3.12')
if ($result.ExitCode -ne 0 -and (Invoke-Capture 'uv' @('python', 'find', '3.12')).ExitCode -ne 0) { Fail "uv could not install Python 3.12: $($result.Output)" }
Write-Ok "Python $((Invoke-Capture 'uv' @('python', 'find', '3.12')).Output)"

foreach ($dir in 'apps\api', 'services\vision') {
    Write-Banner "Python: $dir (uv)"
    if ($SkipVision -and $dir -eq 'services\vision') { Skip "$dir (-SkipVision)"; continue }
    if (-not (Test-Path -LiteralPath (Join-Path $dir 'pyproject.toml'))) { Skip "$dir does not exist yet"; continue }
    if (Test-Ci) { Invoke-Native 'uv' @('sync', '--locked') -WorkingDirectory $dir } else { Invoke-Native 'uv' @('sync') -WorkingDirectory $dir }
}

Write-Banner 'Git hooks'
# The same thing scripts/install-git-hooks.sh does (pnpm install ran it too).
$hooksPath = (Invoke-Capture 'git' @('config', '--get', 'core.hooksPath')).Output
if ($hooksPath -ne 'scripts/git-hooks') {
    Invoke-Native 'git' @('config', 'core.hooksPath', 'scripts/git-hooks')
    Write-Ok 'Git hooks installed (core.hooksPath = scripts/git-hooks)'
} else {
    Write-Ok 'Git hooks already installed'
}
Write-Ok 'Dependencies installed'
exit 0
