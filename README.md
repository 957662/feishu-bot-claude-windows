# feishu-bot-claude-win

Windows-native port of [feishu-bot-claude](../feishu-bot-claude/) — bridges a local
Claude Code TUI session to a dedicated Feishu bot, strict 1:1 per project.

**No WSL, no Cygwin.** Runs on Windows 10/11 with native Python, native `lark-cli.exe`,
and native [`zellij`](https://github.com/zellij-org/zellij) as the terminal multiplexer.

## Architecture differences vs. the macOS edition

| Concern | macOS | Windows |
|---|---|---|
| Session multiplexer | `tmux` | `zellij` |
| Daemon process supervisor | `launchd` plist | Windows Service via [NSSM](https://nssm.cc/) |
| Control channel | Unix domain socket `~/.feishu-bot-claude/control.sock` | TCP loopback `127.0.0.1:<ephemeral>` (port written to `~/.feishu-bot-claude-win/control.port`) |
| Secret storage | macOS Keychain (`security` CLI) | Windows Credential Manager (`win32cred` via pywin32) |
| CLI shim | symlink in `/opt/homebrew/bin/` | `.cmd` shim in `%LOCALAPPDATA%\Programs\feishu-bot-claude-win\` |
| Browser auto-open | `open` | `os.startfile()` (default handler) |

The Feishu protocol code (cards, rendering, rate limit, inbound/outbound pipelines,
event dedup, reaction ack) is **identical** to the macOS edition.

## Prerequisites

Install these before running `setup.ps1`:

| Tool | Install command |
|---|---|
| Python 3.11+ | `winget install Python.Python.3.12` |
| Node.js 16+ | `winget install OpenJS.NodeJS.LTS` |
| NSSM | `winget install NSSM.NSSM` |
| zellij | `winget install zellij-org.zellij`  *(or `scoop install zellij`)* |

`lark-cli` is installed automatically by `setup.ps1` via `npm i -g @larksuite/cli`.

## Install

```powershell
cd path\to\feishu-bot-claude-win
pwsh -ExecutionPolicy Bypass -File .\setup.ps1
```

This:
1. Creates `.venv/` and installs the project (`pip install -e .[win]`)
2. Installs `lark-cli` globally via npm (if not already on PATH)
3. Creates data dir `~\.feishu-bot-claude-win\`
4. Writes a `feishu-bot-claude.cmd` shim into `%LOCALAPPDATA%\Programs\feishu-bot-claude-win\` (added to user PATH)
5. Registers the daemon as a Windows Service named `feishu-bot-claude-win` via NSSM and starts it

Open a **new** PowerShell window (so the new PATH takes effect) and verify:

```powershell
feishu-bot-claude ping
feishu-bot-claude status
```

## Usage

Same surface as the macOS edition:

```powershell
# Bind a new bot to a project
feishu-bot-claude bind myproject-bot --cwd C:\path\to\my-project

# Start the mirror (jsonl → Feishu cards) for an existing binding
feishu-bot-claude start --cwd C:\path\to\my-project

# Spawn zellij + Claude in a new console (this is the "claude TUI" window)
feishu-bot-claude shell --cwd C:\path\to\my-project --dangerously-skip-permissions

# In the new window, Ctrl+P then D to detach (keep session alive in background)
# Reattach later: zellij attach claude-<basename>
```

## Service management

```powershell
# Status / control via NSSM (or use sc.exe)
nssm status  feishu-bot-claude-win
nssm restart feishu-bot-claude-win
nssm stop    feishu-bot-claude-win

# Logs
Get-Content $env:USERPROFILE\.feishu-bot-claude-win\logs\daemon.err.log -Tail 50 -Wait
```

## Uninstall

```powershell
pwsh -ExecutionPolicy Bypass -File .\uninstall.ps1            # keeps bindings + state
pwsh -ExecutionPolicy Bypass -File .\uninstall.ps1 -Purge     # also deletes data dir
```

## Known limitations

- **Multi-user host**: TCP loopback control socket has no per-user ACL. If you share
  a Windows workstation with other users, any local user can talk to the daemon.
  For that scenario, switch to Named Pipes with explicit DACLs (planned, not done).
- **Path encoding**: Claude Code encodes project paths into the `~\.claude\projects\`
  subdirectory name. The convention on Windows uses drive letters
  (`-C--Users-...`); this is handled by `_guess_jsonl_path` reading mtime.
- **zellij detach UX**: Closing the console window kills the zellij session if it's
  attached. Use `Ctrl+P, D` to detach first.
