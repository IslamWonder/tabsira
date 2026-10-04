# Helpers shared by every PowerShell script in scripts/windows. Dot-source it
# after the script's own param block:
#   . "$PSScriptRoot\lib.ps1"
#
# Windows PowerShell 5.1 and PowerShell 7. ASCII only: 5.1 reads a file that has
# no byte-order mark in the system code page. These scripts are the Windows
# counterparts of the shell scripts in scripts/ (the make targets stay the
# reference); they install everything natively, without Docker or WSL.

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
# Tools that are not part of the checkout live beside it, like ../tabsira-artifact.
$ToolsDir = if ($env:TABSIRA_TOOLS) { $env:TABSIRA_TOOLS } else { Join-Path (Split-Path -Parent $RepoRoot) 'tabsira-tools' }
$DownloadDir = Join-Path $ToolsDir 'downloads'
$LogDir = Join-Path $ToolsDir 'logs'
$EnvFile = Join-Path $RepoRoot '.env'
$PgVersion = if ($env:PG_VERSION) { $env:PG_VERSION } else { '18' }
$PgPort = if ($env:PG_PORT) { $env:PG_PORT } else { '5432' }
$PgServiceName = "postgresql-x64-$PgVersion"
# Where libpq reads passwords on Windows. The superuser password the installer
# generated goes there, never into the repository. PGPASSFILE names another
# file (the provisioning passes the invoking user's file to its elevated part).
if (-not $env:PGPASSFILE) { $env:PGPASSFILE = Join-Path $env:APPDATA 'postgresql\pgpass.conf' }
$PgPassFile = $env:PGPASSFILE
$LocalHosts = @('tabsira.test', 'api.tabsira.test', 'admin.tabsira.test')
$HostsFile = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'

# --- Log helpers --------------------------------------------------------
function Write-Log { param([string]$Message) Write-Host "[tabsira] $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "[ ok ] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[warn] $Message" -ForegroundColor Yellow }
function Write-Err { param([string]$Message) Write-Host "[err ] $Message" -ForegroundColor Red }
function Write-Banner {
    param([string]$Title)
    Write-Log ('-' * 54)
    Write-Log $Title
    Write-Log ('-' * 54)
}
function Fail {
    param([string]$Message)
    Write-Err $Message
    exit 1
}
function Skip { param([string]$Message) Write-Warn "skipped: $Message" }

function Test-Command { param([string]$Name) return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Assert-Admin {
    param([string]$Hint = '')
    if (-not (Test-Admin)) { Fail "this script needs an elevated PowerShell (Run as administrator). $Hint" }
}

function Test-Ci { return ($env:CI -eq 'true' -or $env:CI -eq '1' -or $env:JENKINS_BUILD -eq 'true' -or $env:JENKINS_BUILD -eq '1') }

# --- PATH ------------------------------------------------------------------
function Add-PathEntry {
    param([string]$Dir, [switch]$Append)
    if (-not $Dir -or -not (Test-Path -LiteralPath $Dir)) { return }
    $parts = @($env:Path -split ';' | Where-Object { $_ })
    if ($parts -contains $Dir) { return }
    if ($Append) { $env:Path = ($parts + $Dir) -join ';' } else { $env:Path = (@($Dir) + $parts) -join ';' }
}

# Pick up what an installer just added to the user's or the machine's PATH.
function Update-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $merged = @()
    foreach ($p in (($env:Path + ';' + $machine + ';' + $user) -split ';')) {
        if ($p -and ($merged -notcontains $p)) { $merged += $p }
    }
    $env:Path = $merged -join ';'
    # winget's portable packages (uv, mkcert, jq, shfmt) are linked from here.
    Add-PathEntry (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links') -Append
    Add-PathEntry (Join-Path $env:ProgramFiles 'WinGet\Links') -Append
}

# The repository's shell scripts (git hooks, pnpm's prepare, gen-api.sh) need
# Git's bash, not the WSL launcher that System32 puts first on PATH.
function Use-GitBash {
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $git) { return }
    $root = Split-Path -Parent (Split-Path -Parent $git.Source)
    Add-PathEntry (Join-Path $root 'bin')
    Add-PathEntry (Join-Path $root 'mingw64\bin') -Append
    Add-PathEntry (Join-Path $root 'usr\bin') -Append
}

function Set-NodeEnvironment {
    Use-GitBash
    $env:NEXT_TELEMETRY_DISABLED = '1'
    # package.json scripts are written as `VAR=value command`, a POSIX form cmd.exe
    # does not know; pnpm's shell emulator runs them the same way on Windows.
    $env:npm_config_shell_emulator = 'true'
}

function Set-PythonEnvironment {
    # An outer virtual environment makes uv warn that it is not the project's.
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
}

# --- Running programs --------------------------------------------------
# Run a native program and fail when it does; its output streams through.
function Invoke-Native {
    param([string]$File, [string[]]$Arguments = @(), [string]$WorkingDirectory)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    if ($WorkingDirectory) { Push-Location -LiteralPath $WorkingDirectory }
    try {
        & $File @Arguments
        $code = $LASTEXITCODE
    } finally {
        if ($WorkingDirectory) { Pop-Location }
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "$File failed with exit code $code" }
}

# Run a native program and capture everything it printed.
function Invoke-Capture {
    param([string]$File, [string[]]$Arguments = @(), [string]$InputText)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($InputText) {
            $lines = @($InputText | & $File @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        } else {
            $lines = @(& $File @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    return [pscustomobject]@{ Output = ($lines -join "`n").Trim(); Lines = $lines; ExitCode = $code }
}

function ConvertTo-ArgumentString {
    param([string[]]$Arguments)
    $quoted = foreach ($item in $Arguments) {
        if ($item -match '[\s"]') { '"' + ($item -replace '"', '\"') + '"' } else { $item }
    }
    return ($quoted -join ' ')
}

# Run a script of this folder in an elevated window and wait for it. Returns
# its exit code. The window is the same PowerShell as this one.
function Invoke-Elevated {
    param([string]$Script, [string[]]$Arguments = @())
    $shell = (Get-Process -Id $PID).Path
    $list = ConvertTo-ArgumentString (@('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Script) + $Arguments)
    $process = Start-Process -FilePath $shell -ArgumentList $list -Verb RunAs -PassThru
    # Not -Wait: Windows PowerShell would also wait for every descendant, and an
    # installer may leave a background process behind for good.
    $process.WaitForExit()
    return $process.ExitCode
}

function Test-TcpPort {
    param([string]$ComputerName = '127.0.0.1', [int]$Port, [int]$TimeoutMs = 1500)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($ComputerName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function New-RandomHex {
    param([int]$Bytes = 24)
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return (($buffer | ForEach-Object { $_.ToString('x2') }) -join '')
}

# --- Files ---------------------------------------------------------------
function Write-Utf8File {
    param([string]$Path, [string]$Content)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

# Only the current user may read the file (secrets: .env, pgpass.conf).
function Protect-File {
    param([string]$Path)
    try {
        # The access rules alone: Set-Acl would also touch the owner and the
        # audit rules, which a user without SeSecurityPrivilege cannot.
        $file = Get-Item -LiteralPath $Path
        $acl = $file.GetAccessControl([System.Security.AccessControl.AccessControlSections]::Access)
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRule($rule) }
        $me = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($me, 'FullControl', 'Allow')))
        $file.SetAccessControl($acl)
    } catch {
        Write-Warn "could not restrict $Path to you alone: $_"
    }
}

function Get-Download {
    param([string]$Url, [string]$Name, [string]$Sha256, [string]$Md5)
    New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null
    $path = Join-Path $DownloadDir $Name
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Log "Downloading $Name"
        $previous = $ProgressPreference
        $ProgressPreference = 'SilentlyContinue'
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile "$path.part"
        } finally {
            $ProgressPreference = $previous
        }
        Move-Item -Force -LiteralPath "$path.part" -Destination $path
    }
    if ($Sha256 -and (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash -ne $Sha256.ToUpper()) {
        Remove-Item -LiteralPath $path
        Fail "$Name does not match its SHA-256; the download was removed, run again"
    }
    if ($Md5 -and (Get-FileHash -Algorithm MD5 -LiteralPath $path).Hash -ne $Md5.ToUpper()) {
        Remove-Item -LiteralPath $path
        Fail "$Name does not match its MD5; the download was removed, run again"
    }
    return $path
}

function Get-RemoteText {
    param([string]$Url)
    $previous = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try {
        $content = (Invoke-WebRequest -UseBasicParsing -Uri $Url).Content
    } finally {
        $ProgressPreference = $previous
    }
    # A file served without a text content type comes back as bytes.
    if ($content -is [byte[]]) { return [System.Text.Encoding]::UTF8.GetString($content) }
    return [string]$content
}

function Expand-ZipTo {
    param([string]$Zip, [string]$Destination)
    if (Test-Path -LiteralPath $Destination) { Remove-Item -Recurse -Force -LiteralPath $Destination }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Expand-Archive -LiteralPath $Zip -DestinationPath $Destination -Force
}

# --- .env ------------------------------------------------------------------
# KEY from an env file: the last assignment wins, surrounding quotes dropped.
function Get-EnvValue {
    param([string]$File, [string]$Key)
    if (-not (Test-Path -LiteralPath $File)) { return '' }
    $line = Get-Content -LiteralPath $File -Encoding UTF8 | Where-Object { $_.StartsWith("$Key=") } | Select-Object -Last 1
    if (-not $line) { return '' }
    $value = $line.Substring($Key.Length + 1)
    if ($value -match '^"(.*)"$') { return $Matches[1] }
    if ($value -match "^'(.*)'$") { return $Matches[1] }
    return $value
}

# Set KEY=VALUE in an env file: replace the line or append one. UTF-8, LF.
function Set-EnvValue {
    param([string]$File, [string]$Key, [string]$Value)
    $lines = @()
    if (Test-Path -LiteralPath $File) { $lines = @(Get-Content -LiteralPath $File -Encoding UTF8) }
    $done = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].StartsWith("$Key=")) {
            $lines[$i] = "$Key=$Value"
            $done = $true
        }
    }
    if (-not $done) { $lines += "$Key=$Value" }
    Write-Utf8File -Path $File -Content (($lines -join "`n") + "`n")
}

# Load the root .env into this process, except in CI where the pipeline injects
# the values. An empty value leaves the variable unset, as the API expects.
function Import-DotEnv {
    param([string]$File = $EnvFile)
    if (Test-Ci) { return }
    if (-not (Test-Path -LiteralPath $File)) {
        Write-Warn ".env not found at $File (run: scripts\windows\setup-db.ps1)"
        return
    }
    foreach ($line in Get-Content -LiteralPath $File -Encoding UTF8) {
        if ($line -match '^\s*(#|$)') { continue }
        if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $key = $Matches[1]
            $value = $Matches[2].Trim()
            if ($value -match '^"(.*)"$') { $value = $Matches[1] }
            elseif ($value -match "^'(.*)'$") { $value = $Matches[1] }
            [Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
    }
}

# --- winget ----------------------------------------------------------------
function Test-WingetPackage {
    param([string]$Id)
    $result = Invoke-Capture 'winget' @('list', '--id', $Id, '--exact', '--accept-source-agreements', '--disable-interactivity')
    return ($result.ExitCode -eq 0 -and $result.Output -match [regex]::Escape($Id))
}

# Install a winget package when it is missing. Returns $true when it installed.
function Install-WingetPackage {
    param([string]$Id, [string]$Override, [string]$Scope, [string[]]$Extra = @())
    if (-not (Test-Command winget)) { Fail "winget is missing: install 'App Installer' from the Microsoft Store." }
    if (Test-WingetPackage $Id) {
        Write-Ok "$Id is installed"
        return $false
    }
    Write-Log "Installing $Id with winget"
    $list = @('install', '--id', $Id, '--exact', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity') + $Extra
    if ($Override) { $list += @('--override', $Override) }
    try {
        if ($Scope) { Invoke-Native 'winget' ($list + @('--scope', $Scope)) } else { Invoke-Native 'winget' $list }
    } catch {
        # A package whose installer knows no scope is installed the way it comes.
        if (-not $Scope) { throw }
        Write-Warn "$Id did not install with --scope $Scope; trying without"
        Invoke-Native 'winget' $list
    }
    Update-Path
    return $true
}

# --- Node ------------------------------------------------------------------
function Get-NodeMajor {
    if (-not (Test-Command node)) { return 0 }
    $version = (Invoke-Capture 'node' @('--version')).Output -replace '^v', ''
    return [int]($version.Split('.')[0])
}

# Make the active pnpm match the packageManager field of the root package.json.
function Set-PnpmVersion {
    if (-not (Test-Command node)) { Write-Warn 'node not found; cannot verify the pnpm version'; return }
    $packageManager = (Get-Content -LiteralPath (Join-Path $RepoRoot 'package.json') -Raw | ConvertFrom-Json).packageManager
    if (-not $packageManager) { Write-Warn 'no pnpm version pinned in package.json'; return }
    $required = $packageManager.Split('@')[1]
    $current = if (Test-Command pnpm) { (Invoke-Capture 'pnpm' @('--version')).Output } else { 'none' }
    if ($current -eq $required) {
        Write-Ok "pnpm is at the pinned version $current"
        return
    }
    Write-Log "pnpm is $current, package.json pins $required"
    Invoke-Native 'npm' @('install', '-g', "pnpm@$required")
    Update-Path
    Write-Ok "pnpm is now $((Invoke-Capture 'pnpm' @('--version')).Output)"
}

# --- PostgreSQL --------------------------------------------------------
# The EDB installer records every server it installed in the registry.
function Get-PgInstallation {
    $key = 'HKLM:\SOFTWARE\PostgreSQL\Installations'
    if (-not (Test-Path $key)) { return $null }
    foreach ($item in Get-ChildItem $key) {
        $p = Get-ItemProperty -LiteralPath $item.PSPath
        $version = "$($p.Version)"
        if ($version -eq $PgVersion -or $version.StartsWith("$PgVersion.")) {
            $service = if ($p.'Service ID') { $p.'Service ID' } else { $item.PSChildName }
            return [pscustomobject]@{
                BaseDir     = $p.'Base Directory'
                DataDir     = $p.'Data Directory'
                ServiceName = $service
                Version     = $version
            }
        }
    }
    return $null
}

function Get-PgRoot {
    if ($env:TABSIRA_PGROOT) { return $env:TABSIRA_PGROOT }
    $installation = Get-PgInstallation
    if ($installation) { return $installation.BaseDir }
    return (Join-Path $ToolsDir "PostgreSQL\$PgVersion")
}

function Use-PgBin { Add-PathEntry (Join-Path (Get-PgRoot) 'bin') -Append }

# psql as the given role; the password comes from pgpass.conf (-Password for
# a one-off check). SQL that carries a secret goes through -InputSql, never on
# the command line.
function Invoke-Psql {
    param(
        [string]$User = 'postgres', [string]$Database = 'postgres', [string]$Sql, [string]$InputSql,
        [switch]$Tuples, [string]$Password, [string]$PgHost = '127.0.0.1', [string]$Port = $PgPort
    )
    $list = @('-X', '-q', '-v', 'ON_ERROR_STOP=1', '-h', $PgHost, '-p', $Port, '-U', $User, '-d', $Database)
    if ($Tuples) { $list += '-tA' }
    if ($Sql) { $list += @('-c', $Sql) }
    $savedPassword = $env:PGPASSWORD
    $env:PGOPTIONS = '-c client_min_messages=warning'
    $env:PGCONNECT_TIMEOUT = '5'
    if ($Password) { $env:PGPASSWORD = $Password }
    try {
        $result = Invoke-Capture 'psql' $list -InputText $InputSql
    } finally {
        if ($null -ne $savedPassword) { $env:PGPASSWORD = $savedPassword } else { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }
    }
    if ($result.ExitCode -ne 0) { throw "psql ($User@$Database) failed: $($result.Output)" }
    return $result.Output
}

function Test-PsqlAdmin {
    try { return ((Invoke-Psql -Tuples -Sql 'SELECT 1') -eq '1') } catch { return $false }
}

# One line in pgpass.conf: host:port:database:user:password; an existing line
# for the same host, port, database and user is replaced.
function Set-PgPassEntry {
    param([string]$File = $PgPassFile, [string]$HostName = '127.0.0.1', [string]$Port = $PgPort, [string]$Database = '*', [string]$User, [string]$Password)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $File) | Out-Null
    $prefix = "${HostName}:${Port}:${Database}:${User}:"
    $lines = @()
    if (Test-Path -LiteralPath $File) { $lines = @(Get-Content -LiteralPath $File | Where-Object { -not $_.StartsWith($prefix) }) }
    $lines += "$prefix$Password"
    Write-Utf8File -Path $File -Content (($lines -join "`r`n") + "`r`n")
    Protect-File $File
}

# --- hosts -----------------------------------------------------------------
function Get-MissingLocalHosts {
    $content = if (Test-Path -LiteralPath $HostsFile) { @(Get-Content -LiteralPath $HostsFile) } else { @() }
    $missing = @()
    foreach ($name in $LocalHosts) {
        $pattern = '^[^#]*\s' + [regex]::Escape($name) + '(\s|$)'
        if (-not ($content | Where-Object { $_ -match $pattern })) { $missing += $name }
    }
    return $missing
}
