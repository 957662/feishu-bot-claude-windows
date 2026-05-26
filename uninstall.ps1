# uninstall.ps1 — stop service, remove NSSM registration, remove CLI shim.
# Leaves data dir (bindings, state, logs) intact unless -Purge is passed.

param([switch]$Purge)

$ErrorActionPreference = "Continue"

$dataDir = Join-Path $env:USERPROFILE ".feishu-bot-claude-win"
$shimDir = Join-Path $env:LOCALAPPDATA "Programs\feishu-bot-claude-win"
$serviceName = "feishu-bot-claude-win"

Write-Host "==> Stopping service" -ForegroundColor Cyan
& nssm stop $serviceName 2>$null | Out-Null
Start-Sleep -Seconds 1
Write-Host "==> Removing service" -ForegroundColor Cyan
& nssm remove $serviceName confirm 2>$null | Out-Null

if (Test-Path $shimDir) {
    Write-Host "==> Removing CLI shim at $shimDir" -ForegroundColor Cyan
    Remove-Item -Recurse -Force $shimDir
}

if ($Purge -and (Test-Path $dataDir)) {
    Write-Host "==> Purging data dir at $dataDir" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $dataDir
} elseif (Test-Path $dataDir) {
    Write-Host "==> Data dir preserved at $dataDir (use -Purge to delete)" -ForegroundColor Green
}

Write-Host "Done." -ForegroundColor Green
