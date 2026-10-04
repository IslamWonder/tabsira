<#
Put https://tabsira.test, https://api.tabsira.test and https://admin.tabsira.test
behind an nginx of this machine with a certificate from mkcert, what
scripts/setup-nginx-local.sh does with the system nginx on Ubuntu.

  https://tabsira.test       -> web  127.0.0.1:3000
  https://api.tabsira.test   -> API  127.0.0.1:8000
  https://admin.tabsira.test -> API  127.0.0.1:8000, /admin only

nginx for Windows is the zip nginx.org publishes, unpacked into
../tabsira-tools/nginx and run as your own process by scripts\windows\dev.ps1
(no service). Its site configuration is the repository's
nginx/local/tabsira.test.conf with the certificate and log paths of this
machine, and `http2 on;` in the form the current nginx wants.

What it changes, and nothing else:
  - ../tabsira-tools/nginx (the program, its conf\tabsira*.conf, certs, logs)
  - nginx/local/certs/tabsira.test*.pem in the checkout (gitignored)
  - rootCA.pem in the checkout (gitignored), for browsers that keep their own store
  - the mkcert authority in %LOCALAPPDATA%\mkcert, trusted by Windows and
    Chrome/Edge (`mkcert -install`, one time; Windows asks once)
The hosts file needs elevation and is written by provision-system.ps1; this
script only says when the names are missing.

Idempotent. No elevation needed.

Usage: scripts\windows\setup-nginx-local.ps1
#>
. "$PSScriptRoot\lib.ps1"
Update-Path
Use-GitBash

$NginxVersion = '1.30.5'
$NginxUrl = "https://nginx.org/download/nginx-$NginxVersion.zip"
$Site = 'tabsira.test'
$ConfSource = Join-Path $RepoRoot "nginx\local\$Site.conf"
$CertDirLocal = Join-Path $RepoRoot 'nginx\local\certs'
$NginxDir = Join-Path $ToolsDir 'nginx'
$NginxCertDir = Join-Path $NginxDir 'certs'

if (-not (Test-Path -LiteralPath $ConfSource)) { Fail "$ConfSource is missing" }

# --- mkcert authority and certificate ---------------------------------------
Write-Banner 'mkcert'
if (-not (Test-Command mkcert)) { [void](Install-WingetPackage -Id 'FiloSottile.mkcert' -Scope 'user') }
if (-not (Test-Command mkcert)) { Fail 'mkcert could not be installed' }
Write-Log 'Installing and trusting the local mkcert authority (Windows asks once)'
Invoke-Native 'mkcert' @('-install')

$caRoot = (Invoke-Capture 'mkcert' @('-CAROOT')).Output
if ($caRoot -and (Test-Path (Join-Path $caRoot 'rootCA.pem'))) {
    # For importing into a browser that does not use the system store (Firefox).
    Copy-Item -LiteralPath (Join-Path $caRoot 'rootCA.pem') -Destination (Join-Path $RepoRoot 'rootCA.pem') -Force
}

New-Item -ItemType Directory -Force -Path $CertDirLocal | Out-Null
$localCert = Join-Path $CertDirLocal "$Site.pem"
$localKey = Join-Path $CertDirLocal "$Site-key.pem"
function Test-CertificateCoversHosts {
    if (-not ((Test-Path -LiteralPath $localCert) -and (Test-Path -LiteralPath $localKey))) { return $false }
    if (-not (Test-Command openssl)) { return $true }
    $check = Invoke-Capture 'openssl' @('x509', '-in', $localCert, '-noout', '-checkend', '2592000')
    if ($check.ExitCode -ne 0) { return $false }
    $text = (Invoke-Capture 'openssl' @('x509', '-in', $localCert, '-noout', '-ext', 'subjectAltName')).Output
    foreach ($name in $LocalHosts) { if ($text -notlike "*DNS:$name*") { return $false } }
    return $true
}
if (Test-CertificateCoversHosts) {
    Write-Ok "Certificate for $($LocalHosts -join ' ') already exists and is valid"
} else {
    Write-Log "Creating a certificate for $($LocalHosts -join ' ')"
    Invoke-Native 'mkcert' (@('-cert-file', $localCert, '-key-file', $localKey) + $LocalHosts)
}

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
        # Keep conf, certs and logs; replace the program and its default files.
        Get-Process -Name 'nginx' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $nginxExe } | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $NginxDir | Out-Null
    Copy-Item -Path (Join-Path $inner.FullName '*') -Destination $NginxDir -Recurse -Force
    Remove-Item -Recurse -Force -LiteralPath $staging
    Write-Ok "nginx $NginxVersion unpacked into $NginxDir"
}
foreach ($sub in 'conf', 'certs', 'logs', 'temp') { New-Item -ItemType Directory -Force -Path (Join-Path $NginxDir $sub) | Out-Null }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Copy-Item -LiteralPath $localCert -Destination (Join-Path $NginxCertDir "$Site.pem") -Force
Copy-Item -LiteralPath $localKey -Destination (Join-Path $NginxCertDir "$Site-key.pem") -Force

# --- The site configuration, translated for this machine -------------------
function ConvertTo-NginxPath { param([string]$Path) return '"' + ($Path -replace '\\', '/') + '"' }
$certPrefix = ($NginxCertDir -replace '\\', '/') + '/'
$logPrefix = ($LogDir -replace '\\', '/') + '/'
$lines = foreach ($line in (Get-Content -LiteralPath $ConfSource)) {
    # nginx of this version takes `http2 on;` instead of `listen ... http2`.
    if ($line -match '^\s*listen\s+\[::\]') { continue }
    $line = $line -replace '(\s*listen\s+[^;]*?)\s+http2;', '$1;'
    # nginx picks the server by the address a connection arrived on before it
    # looks at the host name: a `listen 127.0.0.1:443` next to `listen 443`
    # takes every connection to 127.0.0.1, where the hosts file sends all
    # three names. The admin server keeps its allow/deny guard.
    $line = $line -replace '(\s*listen\s+)127\.0\.0\.1:443\b', '${1}443'
    # A path with a space must be quoted; every path is, for one rule.
    $line = $line -replace '/etc/nginx/certs/([^\s;]+)', ('"' + $certPrefix + '$1"')
    $line = $line -replace '/var/log/nginx/([^\s;]+)', ('"' + $logPrefix + '$1"')
    $line
    if ($line -match '^\s*ssl_protocols\s') { '    http2 on;' }
}
$siteConf = Join-Path $NginxDir "conf\$Site.conf"
Write-Utf8File -Path $siteConf -Content (($lines -join "`n") + "`n")

$mainConf = Join-Path $NginxDir 'conf\tabsira.conf'
$main = @"
# TABSIRA: the nginx this machine runs for https://tabsira.test (made by
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

Write-Ok "https://tabsira.test, https://api.tabsira.test and https://admin.tabsira.test are configured in $NginxDir"
Write-Host @"

  Web   https://tabsira.test       -> 127.0.0.1:3000
  API   https://api.tabsira.test   -> 127.0.0.1:8000
  Admin https://admin.tabsira.test -> 127.0.0.1:8000 (/admin)

  nginx starts with the apps: scripts\windows\dev.ps1
  Chrome, Edge and curl trust the certificate through the Windows store.
  Firefox: Settings > Privacy & Security > Certificates > View Certificates >
  Authorities > Import > $RepoRoot\rootCA.pem
"@
exit 0
