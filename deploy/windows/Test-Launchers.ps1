# Disposable GitHub runner fixture. Uses no Tailscale account or external service keys.
$ErrorActionPreference = "Stop"
$source = (Get-Location).Path
$target = (git rev-parse HEAD).Trim()
$checkpoint = "e507cb3665af0a191c55f7db62475cc063dd9c40"
$branch = "feature/ai-trading-assistant"
$sourceRef = "refs/heads/$branch"
git update-ref $sourceRef $target
if ($LASTEXITCODE -ne 0) { throw "Could not pin target for updater" }
$legacy = Join-Path $env:RUNNER_TEMP "egx-legacy-checkout"
git clone --shared --no-checkout -- $source $legacy
if ($LASTEXITCODE -ne 0) { throw "Could not clone baseline checkout" }
git -C $legacy switch -C $branch $checkpoint
if ($LASTEXITCODE -ne 0) { throw "Could not check out production checkpoint" }

$env:LOCALAPPDATA = Join-Path $env:RUNNER_TEMP "egx-owner"
New-Item -ItemType Directory $env:LOCALAPPDATA | Out-Null
$homePath = Join-Path $env:LOCALAPPDATA "EGXTradingAssistant"
New-Item -ItemType Directory $homePath | Out-Null
& "$PSScriptRoot/Protect-State.ps1" -Path $homePath
$config = @{
    host = "laptop.example.ts.net"
    owner_hash = ("ephemeral-ci-owner-password" | caddy hash-password).Trim()
    gateway_secret = "ephemeral-ci-test-key-with-sufficient-length"
    environment = @{
        SCANNER_ENABLED = "false"
        THNDR_ENCRYPTION_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        NOTIFICATION_ENCRYPTION_KEY = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="
    }
}
$config | ConvertTo-Json | Set-Content (Join-Path $homePath "private.json") -Encoding utf8
function Invoke-Launcher([string]$Name) {
    & ".\$Name.bat" ci
    if ($LASTEXITCODE -ne 0) { throw "$Name launcher failed" }
}
function Check-Release([string]$Commit, [string]$NextVersion) {
    $pointer = Get-Content (Join-Path $homePath "current.json") | ConvertFrom-Json
    $nextPath = Join-Path $homePath "releases/$Commit/frontend/node_modules/next/package.json"
    if ($pointer.commit -ne $Commit -or (Get-Content -Raw $nextPath | ConvertFrom-Json).version -ne $NextVersion) {
        throw "Unexpected active commit or Next.js version"
    }
}

Push-Location $legacy
try {
    Invoke-Launcher INSTALL
    Check-Release $checkpoint "14.2.35"
    @'
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
from cryptography.fernet import Fernet

root = Path(sys.argv[1])
config = json.loads((root / "private.json").read_text(encoding="utf-8-sig"))
with closing(sqlite3.connect(root / "data/market.db")) as db, db:
    db.execute(
        "INSERT OR REPLACE INTO owner_risk_settings (id, policy, revision) VALUES (1, ?, 7)",
        (json.dumps({"kill_switch": True, "islamic_mode": True}),),
    )
with closing(sqlite3.connect(root / "data/ai_usage.sqlite3")) as db, db:
    db.execute("CREATE TABLE upgrade_fixture (saved TEXT)")
    db.execute("INSERT INTO upgrade_fixture VALUES ('checkpoint-ledger-fixture')")
key = config["environment"]["THNDR_ENCRYPTION_KEY"]
(root / "data/thndr.enc").write_bytes(Fernet(key).encrypt(b'{"error":"CHECKPOINT_VAULT_FIXTURE"}'))
'@ | python - $homePath
    if ($LASTEXITCODE -ne 0) { throw "Could not create synthetic persisted state" }
    $privateHash = (Get-FileHash (Join-Path $homePath "private.json")).Hash
    $vaultHash = (Get-FileHash (Join-Path $homePath "data/thndr.enc")).Hash
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
    Invoke-Launcher UPDATE
    Check-Release $target "16.4.6"
    $health = Invoke-RestMethod $system -Headers $headers
    if ($health.migration.current -ne "0006_order_review" -or -not $health.migration.ready) {
        throw "Unexpected SQLite schema"
    }
    if (-not $health.policy.kill_switch -or -not $health.policy.islamic -or $health.ai.status -ne "DISABLED") {
        throw "Trading policy or zero-cost AI mode was lost"
    }
    if ((Get-FileHash (Join-Path $homePath "private.json")).Hash -ne $privateHash -or
        (Get-FileHash (Join-Path $homePath "data/thndr.enc")).Hash -ne $vaultHash) {
        throw "Settings, encryption keys or encrypted vault changed"
    }
    $api = "http://127.0.0.1:8000/api/v1"
    $thndr = Invoke-RestMethod "$api/integrations/thndr/status" -Headers $headers
    if ($thndr.error -ne "CHECKPOINT_VAULT_FIXTURE" -or $thndr.status -ne "DISCONNECTED") {
        throw "Existing encrypted vault did not load"
    }
    $readiness = Invoke-RestMethod "$api/trading-readiness" -Headers $headers
    if ($readiness.broker_handoff -ne $false) { throw "Broker execution must be disabled" }
    @'
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
root = Path(sys.argv[1])
with closing(sqlite3.connect(root / "data/ai_usage.sqlite3")) as ledger:
    assert ledger.execute("SELECT saved FROM upgrade_fixture").fetchone() == ("checkpoint-ledger-fixture",)
pointer = json.loads((root / "current.json").read_text())
backup = root / "backups" / pointer["backup"]
manifest = json.loads((backup / "manifest.json").read_text())
assert manifest["release"].startswith("e507cb3")
assert {"market.db", "ai_usage.sqlite3", "thndr.enc"} <= set(manifest["files"])
assert len(list((root / "backups").glob("*/manifest.json"))) >= 3
'@ | python - $homePath
    if ($LASTEXITCODE -ne 0) { throw "Existing ledger or verified backup was lost" }
    Write-Host "UPDATE.bat preserved the checkpoint database, risk policy, keys, encrypted vault and backups."

    $password = ConvertTo-SecureString "ephemeral-ci-owner-password" -AsPlainText -Force
    $owner = [PSCredential]::new("owner", $password)
    $gateway = "http://127.0.0.1:8788"
    foreach ($route in @("/", "/stocks/COMI", "/backtesting/results/1",
        "/orders/proposals/00000000-0000-4000-8000-000000000001", "/sw.js")) {
        $response = Invoke-WebRequest "$gateway$route" -Authentication Basic -Credential $owner -AllowUnencryptedAuthentication
        if ($response.StatusCode -ne 200 -or $response.Headers["Cache-Control"] -notmatch "no-store") {
            throw "Route $route did not return authenticated private content"
        }
        if ($route -ne "/sw.js" -and $response.Content -notmatch 'lang="ar" dir="rtl"') {
            throw "Route $route lost the RTL layout"
        }
    }
    Invoke-Launcher RESTART
    Invoke-Launcher STOP
} finally {
    & .\STOP.bat ci
    Pop-Location
    if (Test-Path "$homePath/logs") {
        Get-ChildItem "$homePath/logs" -Filter "*.log" | ForEach-Object {
            Write-Host $_.Name
            Get-Content -LiteralPath $_.FullName -Tail 15
        }
    }
}
