# Disposable GitHub runner fixture. Uses no Tailscale account or external service keys.
$ErrorActionPreference = "Stop"
$env:LOCALAPPDATA = Join-Path $env:RUNNER_TEMP "egx-owner"
New-Item -ItemType Directory $env:LOCALAPPDATA | Out-Null
$homePath = Join-Path $env:LOCALAPPDATA "EGXTradingAssistant"
New-Item -ItemType Directory $homePath | Out-Null
& "$PSScriptRoot/Protect-State.ps1" -Path $homePath
$config = @{
    host = "laptop.example.ts.net"
    owner_hash = ("ephemeral-ci-owner-password" | caddy hash-password).Trim()
    gateway_secret = "ephemeral-ci-test-key-with-sufficient-length"
    environment = @{ SCANNER_ENABLED = "false" }
}
$config | ConvertTo-Json | Set-Content (Join-Path $homePath "private.json") -Encoding utf8
git switch -C feature/ai-trading-assistant
if ($LASTEXITCODE -ne 0) { throw "Could not select disposable checkout" }
function Invoke-Launcher([string]$Name) {
    & ".\$Name.bat" ci
    if ($LASTEXITCODE -ne 0) { throw "$Name launcher failed" }
}
try {
    Invoke-Launcher INSTALL
    Invoke-Launcher START
    Invoke-Launcher STATUS
    $listeners = Get-NetTCPConnection -State Listen -LocalPort 3000,8000,8788
    if (@($listeners).Count -ne 3 -or @($listeners | Where-Object LocalAddress -ne "127.0.0.1").Count) {
        throw "Application services must listen only on IPv4 loopback"
    }
    $headers = @{ "X-EGX-Gateway" = $config.gateway_secret }
    $system = "http://127.0.0.1:8000/api/v1/system"
    $deadline = (Get-Date).AddSeconds(30)
    do {
        $health = Invoke-RestMethod $system -Headers $headers
        if ($health.workers.paper.running -and $health.workers.backtest.running -and $health.workers.notifications.running) {
            break
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    if (-not $health.workers.paper.running -or -not $health.workers.backtest.running -or -not $health.workers.notifications.running) {
        throw "Workers failed to become healthy"
    }
    $paper = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -match " -m app\.workers\.paper_worker$" } |
        Select-Object -First 1
    if (-not $paper) { throw "Paper worker process was not found" }
    $paperSeen = $health.workers.paper.seen
    Stop-Process -Id $paper.ProcessId -Force
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Seconds 1
        $health = Invoke-RestMethod $system -Headers $headers
    } while ($health.workers.paper.seen -le $paperSeen -and (Get-Date) -lt $deadline)
    if ($health.workers.paper.seen -le $paperSeen) { throw "Paper worker did not recover" }
    Invoke-Launcher BACKUP
    Invoke-Launcher RESTART
    Invoke-Launcher STOP
} finally {
    & .\STOP.bat ci
    if (Test-Path "$homePath/logs") {
        Get-ChildItem "$homePath/logs" -Filter "*.log" | ForEach-Object {
            Write-Host $_.Name
            Get-Content -LiteralPath $_.FullName -Tail 15
        }
    }
}
