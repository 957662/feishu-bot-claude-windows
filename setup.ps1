# setup.ps1 — install/upgrade/uninstall/doctor for feishu-bot-claude-win.
# 全自动:用 winget 装系统依赖,npm 装 CLI 工具,NSSM 注册服务.
#
# 跑法:
#   pwsh -ExecutionPolicy Bypass -File .\setup.ps1            交互式
#   pwsh -ExecutionPolicy Bypass -File .\setup.ps1 -Yes       非交互(全 Y)
#   pwsh -ExecutionPolicy Bypass -File .\setup.ps1 -Doctor    只检测
#   pwsh -ExecutionPolicy Bypass -File .\setup.ps1 -Uninstall 卸载
#
# 注意: NSSM 服务注册需要管理员权限. 脚本检测到非管理员会跳过服务部分,
# 让你装完依赖后再用管理员 PowerShell 重跑此脚本.

param(
    [string]$Action = "install",
    [switch]$Yes,
    [switch]$Doctor,
    [switch]$Uninstall
)

if ($Doctor)    { $Action = "doctor" }
if ($Uninstall) { $Action = "uninstall" }

$ErrorActionPreference = "Stop"

$root        = $PSScriptRoot
$venv        = Join-Path $root ".venv"
$dataDir     = Join-Path $env:USERPROFILE ".feishu-bot-claude-win"
$shimDir     = Join-Path $env:LOCALAPPDATA "Programs\feishu-bot-claude-win"
$serviceName = "feishu-bot-claude-win"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Confirm-Auto {
    param([string]$Message)
    if ($Yes) {
        Write-Host "[auto-yes] $Message" -ForegroundColor DarkGray
        return $true
    }
    $resp = Read-Host "$Message [Y/n]"
    return ($resp -notmatch '^[nN]')
}

function Test-Admin {
    return ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent() `
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Refresh PATH so binaries installed in this session become visible without
# restarting PowerShell.
function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Ensure-Winget {
    if (Get-Command winget -ErrorAction SilentlyContinue) { return }
    Write-Host ""
    Write-Host "winget 没找到." -ForegroundColor Red
    Write-Host "winget 是 Windows 10/11 自带的 'App Installer'. 解决:" -ForegroundColor Yellow
    Write-Host "  1. 打开 Microsoft Store"
    Write-Host "  2. 搜索 'App Installer' 并安装"
    Write-Host "  3. 重启 PowerShell 后重跑此脚本"
    exit 1
}

function Ensure-WingetPkg {
    param(
        [Parameter(Mandatory)] [string]$Cmd,
        [Parameter(Mandatory)] [string]$PkgId
    )
    if (Get-Command $Cmd -ErrorAction SilentlyContinue) {
        Write-Host "[ok] $Cmd : $((Get-Command $Cmd).Source)" -ForegroundColor Green
        return
    }
    Ensure-Winget
    if (-not (Confirm-Auto "缺 $Cmd, 用 winget install $PkgId 自动装吗?")) {
        Write-Error "没 $Cmd 没法继续"
        exit 1
    }
    & winget install --id $PkgId --silent --accept-source-agreements --accept-package-agreements
    Refresh-Path
    if (-not (Get-Command $Cmd -ErrorAction SilentlyContinue)) {
        Write-Warning "$Cmd 装好了但当前会话仍找不到. 关掉这个 PowerShell, 重开一个再跑此脚本."
        exit 1
    }
}

function Ensure-NpmGlobal {
    param(
        [Parameter(Mandatory)] [string]$Pkg,
        [Parameter(Mandatory)] [string]$Bin
    )
    if (Get-Command $Bin -ErrorAction SilentlyContinue) {
        Write-Host "[ok] $Bin : $((Get-Command $Bin).Source)" -ForegroundColor Green
        return
    }
    if (-not (Confirm-Auto "缺 $Bin, 用 npm i -g $Pkg 装吗?")) {
        return
    }
    & npm install -g $Pkg
    Refresh-Path
}

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

function Invoke-Install {
    Write-Host "==> 1. 系统依赖 (winget)" -ForegroundColor Cyan
    Ensure-WingetPkg -Cmd "python" -PkgId "Python.Python.3.12"
    Ensure-WingetPkg -Cmd "node"   -PkgId "OpenJS.NodeJS.LTS"
    Ensure-WingetPkg -Cmd "nssm"   -PkgId "NSSM.NSSM"
    Ensure-WingetPkg -Cmd "zellij" -PkgId "zellij-org.zellij"

    Write-Host ""
    Write-Host "==> 2. npm 全局工具" -ForegroundColor Cyan
    Ensure-NpmGlobal -Pkg "@larksuite/cli"           -Bin "lark-cli"
    Ensure-NpmGlobal -Pkg "@anthropic-ai/claude-code" -Bin "claude"
    if (Confirm-Auto "可选: 装 mermaid-cli 让机器人把 mermaid 代码块渲染成图?") {
        Ensure-NpmGlobal -Pkg "@mermaid-js/mermaid-cli" -Bin "mmdc"
    }

    Write-Host ""
    Write-Host "==> 3. Python venv + 项目本体" -ForegroundColor Cyan
    if (-not (Test-Path $venv)) {
        & python -m venv $venv
    }
    $pyExe = Join-Path $venv "Scripts\python.exe"
    & $pyExe -m pip install --upgrade pip
    & $pyExe -m pip install -e ".[win]"

    Write-Host ""
    Write-Host "==> 4. 数据目录 + CLI shim" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $dataDir "logs") | Out-Null
    New-Item -ItemType Directory -Force -Path $shimDir | Out-Null

    $shimPath = Join-Path $shimDir "feishu-bot-claude.cmd"
    @"
@echo off
"$pyExe" -m feishu_bot_claude_win %*
"@ | Set-Content -Path $shimPath -Encoding ASCII -NoNewline
    Write-Host "[ok] CLI shim: $shimPath" -ForegroundColor Green

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$shimDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$shimDir", "User")
        Write-Host "[ok] $shimDir 加进了 User PATH (重开 shell 后生效)" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "==> 5. Windows 服务 (NSSM)" -ForegroundColor Cyan
    if (-not (Test-Admin)) {
        Write-Warning @"
非管理员运行,跳过服务注册.

依赖和本体都已装好. 要让 daemon 开机自启,关掉此窗口,
右键 PowerShell -> 以管理员身份运行, 然后:
  cd '$root'
  .\setup.ps1
"@
        return
    }

    & nssm install $serviceName $pyExe "-m" "feishu_bot_claude_win" "daemon" 2>$null | Out-Null
    & nssm set $serviceName AppDirectory $root | Out-Null
    & nssm set $serviceName AppStdout (Join-Path $dataDir "logs\daemon.out.log") | Out-Null
    & nssm set $serviceName AppStderr (Join-Path $dataDir "logs\daemon.err.log") | Out-Null
    & nssm set $serviceName AppRotateFiles 1 | Out-Null
    & nssm set $serviceName AppRotateBytes 10485760 | Out-Null
    & nssm set $serviceName Start SERVICE_AUTO_START | Out-Null
    & nssm set $serviceName AppEnvironmentExtra "FEISHU_BOT_CLAUDE_DATA_DIR=$dataDir" | Out-Null

    & nssm start $serviceName 2>$null | Out-Null
    Start-Sleep -Seconds 2
    $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {
        Write-Host "[ok] 服务正在运行" -ForegroundColor Green
    } else {
        Write-Warning "服务状态: $($svc.Status). 看日志: $dataDir\logs\"
    }

    Write-Host ""
    Write-Host "✅ feishu-bot-claude-win installed." -ForegroundColor Green
    Write-Host "Try:" -ForegroundColor Cyan
    Write-Host "  feishu-bot-claude ping"
    Write-Host "  feishu-bot-claude bind <name> --cwd <project-path>"
    Write-Host "  feishu-bot-claude shell --cwd <project-path>"
}

function Invoke-Uninstall {
    if (-not (Test-Admin)) {
        Write-Error "卸载需要管理员权限. 用管理员 PowerShell 重跑."
        exit 1
    }
    Write-Host "==> 停止 + 卸载服务" -ForegroundColor Cyan
    & nssm stop   $serviceName 2>$null | Out-Null
    & nssm remove $serviceName confirm 2>$null | Out-Null

    Write-Host "==> 删 CLI shim" -ForegroundColor Cyan
    Remove-Item -Force -Path (Join-Path $shimDir "feishu-bot-claude.cmd") -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "✅ Daemon stopped + service removed." -ForegroundColor Green
    Write-Host "Bindings kept at: $dataDir\bindings.toml" -ForegroundColor Yellow
}

function Invoke-Doctor {
    function Probe { param($Name, $Cmd)
        $c = Get-Command $Cmd -ErrorAction SilentlyContinue
        if ($c) { "[ok]   {0,-22} {1}" -f $Name, $c.Source }
        else    { "[MISS] {0,-22} not on PATH" -f $Name }
    }
    Write-Host (Probe "python"            "python")
    Write-Host (Probe "node"              "node")
    Write-Host (Probe "npm"               "npm")
    Write-Host (Probe "nssm"              "nssm")
    Write-Host (Probe "zellij"            "zellij")
    Write-Host (Probe "lark-cli"          "lark-cli")
    Write-Host (Probe "claude"            "claude")
    Write-Host (Probe "mmdc (optional)"   "mmdc")
    Write-Host (Probe "feishu-bot-claude" "feishu-bot-claude")

    $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host ("[svc]  {0,-22} {1}" -f $serviceName, $svc.Status)
    } else {
        Write-Host ("[svc]  {0,-22} not installed" -f $serviceName)
    }

    if (Test-Path (Join-Path $dataDir "bindings.toml")) {
        Write-Host ("[file] {0,-22} OK" -f "bindings.toml")
    } else {
        Write-Host ("[file] {0,-22} NONE" -f "bindings.toml")
    }
}

switch ($Action.ToLower()) {
    "install"    { Invoke-Install }
    "uninstall"  { Invoke-Uninstall }
    "doctor"     { Invoke-Doctor }
    default      {
        Write-Host "Usage: setup.ps1 [-Action install|uninstall|doctor] [-Yes]" -ForegroundColor Yellow
        exit 1
    }
}
