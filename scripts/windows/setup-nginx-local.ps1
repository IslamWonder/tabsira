<#
Put http://tabsira.test, http://api.tabsira.test and http://admin.tabsira.test
behind an nginx of this machine, on port 80 and without TLS (decision 49): what
scripts/setup-nginx-local.sh does with the system nginx on Ubuntu.

  http://tabsira.test       -> web  127.0.0.1:3000
  http://api.tabsira.test   -> API  127.0.0.1:8000
  http://admin.tabsira.test -> API  127.0.0.1:8000, /admin only

nginx for Windows is the zip nginx.org publishes, unpacked into
../tabsira-tools/nginx and run as your own process by scripts\windows\dev.ps1
(no service). Its site configuration is the repository's
nginx/local/tabsira.test.conf with the log paths of this machine and without
the IPv6 listens.

What it changes, and nothing else: ../tabsira-tools/nginx (the program, its
conf\tabsira*.conf, logs). A certificate an earlier HTTPS setup left in
nginx/local/certs or ../tabsira-tools/nginx/certs is not touched; nothing
reads it any more. The hosts file needs elevation and is written by
provision-system.ps1; this script only says when the names are missing.

Idempotent. No elevation needed.

Usage: scripts\windows\setup-nginx-local.ps1
#>
. "$PSScriptRoot\lib.ps1"
Update-Path

$NginxVersion = '1.30.5'
$NginxUrl = "https://nginx.org/download/nginx-$NginxVersion.zip"
$Site = 'tabsira.test'
$ConfSource = Join-Path $RepoRoot "nginx\local\$Site.conf"
$NginxDir = Join-Path $ToolsDir 'nginx'

if (-not (Test-Path -LiteralPath $ConfSource)) { Fail "$ConfSource is missing" }

# --- nginx for Windows ------------------------------------------------------
Write-Banner "nginx $NginxVersion"
$nginxExe = Join-Path $NginxDir 'nginx.exe'
$currentVersion = ''
if (Test-Path -LiteralPath $nginxExe) {
    $currentVersion = ((Invoke-Capture $nginxExe @('-v')).Output -replace '^.*nginx/', '').Trim()
}
if ($currentVersion -eq $NginxVersion) {
    Write-Ok "nginx $currentVersion is at $NginxDir"
} else {
    $zip = Get-Download -Url $NginxUrl -Name "nginx-$NginxVersion.zip"
    $staging = Join-Path $ToolsDir 'build\nginx'
    Expand-ZipTo $zip $staging
    $inner = Get-ChildItem -LiteralPath $staging -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'nginx.exe') } | Select-Object -First 1
    if (-not $inner) { Fail 'no nginx.exe inside the nginx zip' }
    if (Test-Path -LiteralPath $nginxExe) {
        # Keep conf and logs; replace the program and its default files.
        Get-Process -Name 'nginx' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $nginxExe } | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $NginxDir | Out-Null
    Copy-Item -Path (Join-Path $inner.FullName '*') -Destination $NginxDir -Recurse -Force
    Remove-Item -Recurse -Force -LiteralPath $staging
    Write-Ok "nginx $NginxVersion unpacked into $NginxDir"
}
foreach ($sub in 'conf', 'logs', 'temp') { New-Item -ItemType Directory -Force -Path (Join-Path $NginxDir $sub) | Out-Null }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# --- The site configuration, translated for this machine -------------------
function ConvertTo-NginxPath { param([string]$Path) return '"' + ($Path -replace '\\', '/') + '"' }
$logPrefix = ($LogDir -replace '\\', '/') + '/'
$lines = foreach ($line in (Get-Content -LiteralPath $ConfSource)) {
    # One socket per port is enough on this machine.
    if ($line -match '^\s*listen\s+\[::\]') { continue }
    # A path with a space must be quoted; every path is, for one rule.
    $line -replace '/var/log/nginx/([^\s;]+)', ('"' + $logPrefix + '$1"')
}
$siteConf = Join-Path $NginxDir "conf\$Site.conf"
Write-Utf8File -Path $siteConf -Content (($lines -join "`n") + "`n")

$mainConf = Join-Path $NginxDir 'conf\tabsira.conf'
$main = @"
# TABSIRA: the nginx this machine runs for http://tabsira.test (made by
# scripts\windows\setup-nginx-local.ps1; edit nginx/local/tabsira.test.conf in
# the repository, not this file). Started and stopped by scripts\windows\dev.ps1.
worker_processes 1;
error_log $(ConvertTo-NginxPath (Join-Path $LogDir 'nginx.error.log')) warn;
pid logs/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include mime.types;
    default_type application/octet-stream;
    sendfile on;
    keepalive_timeout 65;
    client_body_temp_path temp/client_body;
    proxy_temp_path temp/proxy;
    fastcgi_temp_path temp/fastcgi;
    uwsgi_temp_path temp/uwsgi;
    scgi_temp_path temp/scgi;

    include $Site.conf;
}
"@
Write-Utf8File -Path $mainConf -Content ($main -replace "`r`n", "`n")

Write-Log 'Validating the nginx configuration'
Invoke-Native $nginxExe @('-t', '-p', $NginxDir, '-c', 'conf\tabsira.conf') -WorkingDirectory $NginxDir

$running = Get-Process -Name 'nginx' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $nginxExe }
if ($running) {
    Write-Log 'Reloading the running nginx'
    Invoke-Native $nginxExe @('-s', 'reload', '-p', $NginxDir, '-c', 'conf\tabsira.conf') -WorkingDirectory $NginxDir
}

$missing = Get-MissingLocalHosts
if ($missing.Count -gt 0) {
    Write-Warn "not in ${HostsFile}: $($missing -join ' '). Run scripts\windows\provision-dev.ps1 (elevated part), or add the line: 127.0.0.1 $($LocalHosts -join ' ')"
}
if (-not $running -and (Test-TcpPort -Port 80 -TimeoutMs 500)) {
    Write-Warn 'something else listens on port 80 (IIS, another proxy?); nginx will not start until it is stopped'
}

Write-Ok "http://tabsira.test, http://api.tabsira.test and http://admin.tabsira.test are configured in $NginxDir"
Write-Host @"

  Web   http://tabsira.test       -> 127.0.0.1:3000
  API   http://api.tabsira.test   -> 127.0.0.1:8000
  Admin http://admin.tabsira.test -> 127.0.0.1:8000 (/admin)

  nginx starts with the apps: scripts\windows\dev.ps1
"@
exit 0
