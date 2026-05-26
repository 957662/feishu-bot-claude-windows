# setup.ps1 — install feishu-bot-claude-win in an isolated venv,
# install lark-cli (npm) + zellij (cargo or scoop or chocolatey or manual),
# register a Windows Service via NSSM, and create a per-user CLI shim.
#
# Run from this directory:
#   pwsh -ExecutionPolicy Bypass -File .\setup.ps1
#
# Prereqs the script checks for and errors out on (does not auto-install):
#   - Python 3.11+ on PATH
#   - Node.js 16+ on PATH (for npm i -g @larksuite/cli)
#   - NSSM on PATH (winget install NSSM.NSSM, or choco install nssm)
#   - zellij.exe on PATH (winget install zellij-org.zellij, or scoop install zellij)
#
# Idempotent: rerun is safe; venv is reused, service is reconfigured.

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$venv = Join-Path $root ".venv"
$dataDir = Join-Path $env:USERPROFILE ".feishu-bot-claude-win"
$shimDir = Join-Path $env:LOCALAPPDATA "Programs\feishu-bot-claude-win"
$serviceName = "feishu-bot-claude-win"

function Require-Cmd {
    param([string]$cmd, [string]$installHint)
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "$cmd not found on PATH. Install hint: $installHint"
        exit 1
    }
}

Write-Host "==> Checking prerequisites..." -ForegroundColor Cyan
Require-Cmd "python"  "Download from python.org (3.11+), or 'winget install Python.Python.3.12'"
Require-Cmd "npm"     "'winget install OpenJS.NodeJS.LTS'"
Require-Cmd "nssm"    "'winget install NSSM.NSSM' or 'choco install nssm'"
Require-Cmd "zellij"  "'winget install zellij-org.zellij' or 'scoop install zellij'"

# 1. Python venv
Write-Host "==> Creating venv at $venv" -ForegroundColor Cyan
if (-not (Test-Path $venv)) {
    python -m venv $venv
}
$pyExe = Join-Path $venv "Scripts\python.exe"
& $pyExe -m pip install --upgrade pip
& $pyExe -m pip install -e ".[win]"

# 2. lark-cli (global npm install — same as macOS edition)
if (-not (Get-Command "lark-cli" -ErrorAction SilentlyContinue)) {
    Write-Host "==> Installing @larksuite/cli globally via npm" -ForegroundColor Cyan
    npm i -g "@larksuite/cli"
} else {
    Write-Host "==> lark-cli already on PATH" -ForegroundColor Green
}

# 3. Data dir
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dataDir "logs") | Out-Null

# 4. CLI shim (so `feishu-bot-claude` runs the venv's entry point)
New-Item -ItemType Directory -Force -Path $shimDir | Out-Null
$shimPath = Join-Path $shimDir "feishu-bot-claude.cmd"
@"
@echo off
"$pyExe" -m feishu_bot_claude_win %*
"@ | Set-Content -Path $shimPath -Encoding ASCII -NoNewline
Write-Host "==> CLI shim written: $shimPath" -ForegroundColor Green

# Make sure the shim dir is on the user's PATH.
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$shimDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$shimDir", "User")
    Write-Host "==> Added $shimDir to User PATH (restart shell to pick up)" -ForegroundColor Yellow
}

# 5. NSSM service
Write-Host "==> Installing Windows Service '$serviceName' via NSSM" -ForegroundColor Cyan
# nssm install is idempotent: 'set' just updates the existing definition.
& nssm install $serviceName $pyExe "-m" "feishu_bot_claude_win" "daemon" 2>$null | Out-Null
& nssm set $serviceName AppDirectory $root | Out-Null
& nssm set $serviceName AppStdout (Join-Path $dataDir "logs\daemon.out.log") | Out-Null
& nssm set $serviceName AppStderr (Join-Path $dataDir "logs\daemon.err.log") | Out-Null
& nssm set $serviceName AppRotateFiles 1 | Out-Null
& nssm set $serviceName AppRotateBytes 10485760 | Out-Null   # 10MB
& nssm set $serviceName Start SERVICE_AUTO_START | Out-Null
& nssm set $serviceName AppEnvironmentExtra "FEISHU_BOT_CLAUDE_DATA_DIR=$dataDir" | Out-Null

Write-Host "==> Starting service" -ForegroundColor Cyan
& nssm start $serviceName 2>$null | Out-Null
Start-Sleep -Seconds 2
$svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host "==> Service is running" -ForegroundColor Green
} else {
    Write-Host "==> Service status: $($svc.Status). Check logs at $dataDir\logs\" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup done. Try:" -ForegroundColor Green
Write-Host "  feishu-bot-claude ping"
Write-Host "  feishu-bot-claude bind <name> --cwd <project-path>"
Write-Host "  feishu-bot-claude shell --cwd <project-path>"
