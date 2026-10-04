<#
Install a Redis-compatible server on 127.0.0.1:6379 for the scan queue and the
progress stream (decision 21). Redis itself publishes no Windows build, so this
is Memurai Developer (Redis 7 compatible, free for development), through
winget, as the Windows service "Memurai", started automatically, with no
firewall rule: the queue is reached from this machine only.

Idempotent. Needs an elevated PowerShell.

Usage: scripts\windows\install-redis.ps1
#>
. "$PSScriptRoot\lib.ps1"
Assert-Admin 'Run scripts\windows\provision-dev.ps1, which asks for elevation itself.'

$RedisPort = 6379

Write-Banner 'Redis (Memurai Developer)'
if (Test-TcpPort -Port $RedisPort) {
    Write-Ok "something already answers on 127.0.0.1:$RedisPort; leaving it alone"
    exit 0
}

[void](Install-WingetPackage -Id 'Memurai.MemuraiDeveloper' -Override "/quiet /norestart ADD_FIREWALL_RULE=0 PORT=$RedisPort")

$service = Get-Service -Name 'Memurai' -ErrorAction SilentlyContinue
if (-not $service) { Fail 'the Memurai service does not exist after the install' }
Set-Service -Name 'Memurai' -StartupType Automatic
if ($service.Status -ne 'Running') {
    Write-Log 'Starting the Memurai service'
    Start-Service -Name 'Memurai'
}
for ($i = 0; $i -lt 20; $i++) {
    if (Test-TcpPort -Port $RedisPort) { break }
    Start-Sleep -Seconds 1
}
if (-not (Test-TcpPort -Port $RedisPort)) { Fail "nothing answers on 127.0.0.1:$RedisPort after 20 seconds (service Memurai)" }

$cli = Get-ChildItem -Path (Join-Path $env:ProgramFiles 'Memurai') -Filter 'memurai-cli.exe' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($cli) {
    $pong = (Invoke-Capture $cli.FullName @('-h', '127.0.0.1', '-p', "$RedisPort", 'ping')).Output
    if ($pong -ne 'PONG') { Fail "memurai-cli ping answered '$pong'" }
}
Write-Ok "Redis-compatible server answers on 127.0.0.1:$RedisPort"
exit 0
