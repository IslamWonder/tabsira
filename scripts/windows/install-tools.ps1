<#
The developer tools that install for the user alone, no elevation: uv, the
pnpm pinned in package.json, and the quality tools the shell scripts and the
git hooks look for (shfmt, shellcheck, gitleaks, jq). Node itself comes
from provision-system.ps1 (it is a machine-wide installer); here it is checked.

Idempotent.

Usage: scripts\windows\install-tools.ps1 [-NoQualityTools]
#>
param([switch]$NoQualityTools)
. "$PSScriptRoot\lib.ps1"
Update-Path

Write-Banner 'uv'
[void](Install-WingetPackage -Id 'astral-sh.uv' -Scope 'user')
if (-not (Test-Command uv)) { Fail 'uv is not on PATH after the install; open a new terminal and run again' }
Write-Ok (Invoke-Capture 'uv' @('--version')).Output

Write-Banner 'Node and pnpm'
$major = Get-NodeMajor
if ($major -eq 24) {
    Write-Ok "node $((Invoke-Capture 'node' @('--version')).Output)"
} elseif ($major -ge 24) {
    Write-Warn "node is v$major; .nvmrc asks for 24 (scripts\windows\provision-dev.ps1 installs it)"
} else {
    Fail 'Node 24 is required (see .nvmrc): run scripts\windows\provision-dev.ps1'
}
Set-PnpmVersion

if ($NoQualityTools) {
    Skip 'quality tools (-NoQualityTools)'
} else {
    Write-Banner 'Quality tools'
    foreach ($tool in @(
            @{ Id = 'mvdan.shfmt'; Command = 'shfmt' },
            @{ Id = 'koalaman.shellcheck'; Command = 'shellcheck' },
            @{ Id = 'Gitleaks.Gitleaks'; Command = 'gitleaks' },
            @{ Id = 'jqlang.jq'; Command = 'jq' }
        )) {
        if (Test-Command $tool.Command) { Write-Ok "$($tool.Command) is installed"; continue }
        try { [void](Install-WingetPackage -Id $tool.Id -Scope 'user') } catch { Write-Warn "$($tool.Id) could not be installed: $_" }
    }
    Write-Warn 'typos has no winget package; the lint of the Markdown spelling is left to CI'
}
Write-Ok 'Tools installed'
exit 0
