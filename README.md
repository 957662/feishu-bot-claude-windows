# feishu-bot-claude-windows

> **让本地的 Claude Code,在飞书里随时随地遥控 —— Windows 原生版。**
> 一个项目一个专属机器人。**不用 WSL,不用 Cygwin**,纯 Windows 10/11 原生。

[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)](https://github.com/957662/feishu-bot-claude-windows)
[![Python](https://img.shields.io/badge/python-3.11%2B-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

👉 **macOS 用户**:请使用姊妹仓库 [feishu-bot-claude](https://github.com/957662/feishu-bot-claude)

---

## 📖 目录

- [它到底是什么](#-它到底是什么)
- [典型使用场景](#-典型使用场景)
- [跟 macOS 版的关系](#-跟-macos-版的关系)
- [整体架构图](#-整体架构图)
- [前置准备](#-前置准备)
- [安装](#-安装)
- [第一次使用:零到能用全流程](#-第一次使用零到能用全流程)
- [日常使用](#-日常使用)
- [常用命令大全](#-常用命令大全)
- [服务管理](#-服务管理)
- [卸载](#-卸载)
- [架构详解(进阶)](#-架构详解进阶)
- [常见问题 FAQ](#-常见问题-faq)
- [故障排查](#-故障排查)
- [开发与测试](#-开发与测试)
- [License](#license)

---

## 🤔 它到底是什么

简单说:**你 Windows 电脑上的 Claude Code,跟飞书绑定起来**。

打个比方:
- 平时用 Claude Code,你得坐在电脑前的 PowerShell 里跟它对话
- 现在,你出门、坐地铁、躺床上,打开飞书 App,就能跟电脑上那个正在跑的 Claude 继续对话
- Claude 干啥(读文件、改代码、跑命令)你在飞书里看得清清楚楚
- 你想让 Claude 干啥,在飞书里发消息就行

技术上说:
- 给某个**项目目录**绑定**一个专属飞书机器人**
- 项目里 Claude TUI 产生的每一轮对话,被实时镜像成飞书"交互卡片"
- 你在飞书里发的消息,被反向注入到那个 TUI,Claude 看到就响应
- 双向打通,**一个项目一个机器人,严格 1 对 1 不串场**

## 🎯 典型使用场景

| 场景 | 怎么用 |
|---|---|
| 🚇 通勤路上,Claude 在公司 Windows 工作站跑长任务 | 飞书里看进度,需要时插话指挥 |
| 🛋️ 下班想瘫沙发上,但 Claude 还在干活 | 不用打开电脑,手机飞书继续 |
| 🏠 远程办公,临时要让家里电脑跑个调研 | 在公司飞书里直接发任务 |
| 👥 多个项目同时跑 | 每个项目一个机器人,飞书侧边栏自动分流 |

## 🆚 跟 macOS 版的关系

**上层逻辑完全一样**(卡片渲染、入站/出站流水线、速率限制、事件去重、reaction)是逐字相同的。

**底层组件全换成 Windows 原生**:

| 组件 | macOS 版 | Windows 版 |
|---|---|---|
| 会话多路复用器 | `tmux` | [`zellij`](https://github.com/zellij-org/zellij) |
| Daemon 进程守护 | `launchd` plist | [NSSM](https://nssm.cc/) 注册的 Windows Service |
| 控制通道 | Unix 域套接字 `~/.feishu-bot-claude/control.sock` | TCP loopback `127.0.0.1:<动态端口>`(端口写入 `~/.feishu-bot-claude-win/control.port`) |
| 密钥存储 | macOS Keychain (`security` CLI) | Windows 凭据管理器 (`win32cred` via pywin32) |
| CLI 入口 | `/opt/homebrew/bin/` 软链接 | `%LOCALAPPDATA%\Programs\…` 下的 `.cmd` shim |
| 浏览器自动打开 | `open` | `os.startfile()`(走系统默认处理程序) |

## 🗺️ 整体架构图

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          你的 Windows 电脑                                 │
│                                                                            │
│  ┌──────────────────────────┐                                              │
│  │ Windows Terminal /        │                                             │
│  │ PowerShell                │                                             │
│  │                           │                                             │
│  │  zellij session          │                                              │
│  │  ┌─────────────────────┐ │                                              │
│  │  │   Claude Code TUI   │◀┼─── action write-chars + write 13(Enter) ──┐ │
│  │  └──────────┬──────────┘ │                                            │ │
│  └─────────────┼────────────┘                                            │ │
│                │ 写 jsonl                                                 │ │
│                ▼                                                          │ │
│  %USERPROFILE%\.claude\projects\<encoded-cwd>\*.jsonl                     │ │
│                │                                                          │ │
│                │ tail -f                                                  │ │
│                ▼                                                          │ │
│  ┌─────────────────────────────────────────────────────────────────┐     │ │
│  │            feishu-bot-claude-win daemon                         │     │ │
│  │       (NSSM service: "feishu-bot-claude-win")                   │     │ │
│  │                                                                 │     │ │
│  │   ┌─────────────────┐      ┌─────────────────────────┐         │     │ │
│  │   │  outbound 流水线 │      │     inbound 流水线      │         │     │ │
│  │   │                 │      │                         │         │     │ │
│  │   │ jsonl → turn   │      │ lark-cli event consume  │         │     │ │
│  │   │   → 渲染卡片    │      │   → event_id 去重       │         │     │ │
│  │   │   → 速率限制    │      │   → ❤️ reaction ack    │         │     │ │
│  │   │   → 发送/更新   │      │   → zellij write-chars ──────────┘     │ │
│  │   └────────┬────────┘      └────────────▲────────────┘         │       │
│  │            │                            │                      │       │
│  │   ┌────────┴────────────────────────────┴────────────┐         │       │
│  │   │   TCP loopback: 127.0.0.1:<动态端口>             │         │       │
│  │   │   端口写入 %USERPROFILE%\.feishu-bot-claude-win\ │         │       │
│  │   │            control.port                          │         │       │
│  │   └──────────────────────────────────────────────────┘         │       │
│  └─────────┬──────────────────────────────────────────────────────┘       │
│            │ lark-cli messages-send / event consume                       │
│            ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐         │
│  │              lark-cli.exe(npm 全局,Feishu CLI)              │         │
│  └─────────────────────────┬────────────────────────────────────┘         │
└────────────────────────────┼──────────────────────────────────────────────┘
                             │
                             │ HTTPS / WSS
                             ▼
                ┌─────────────────────────────┐
                │   open.feishu.cn (飞书云)    │
                │   - IM API (发卡 / 收消息)  │
                │   - 事件订阅推送(WSS)        │
                └──────────────┬──────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │     飞书 App (你手机/PC)     │
                │   ┌──────────────────────┐   │
                │   │   机器人聊天框      │   │
                │   │ 🤖 my-project        │   │
                │   │                      │   │
                │   │ [卡片] Claude 输出   │   │
                │   │  你的输入...         │   │
                │   └──────────────────────┘   │
                └──────────────────────────────┘
```

**核心思路一句话**:Claude 写 jsonl,daemon tail jsonl → 推飞书;飞书事件推 daemon → zellij 注键。

## 🛠️ 前置准备

要跑起来,你需要装这些(setup.ps1 会检查,缺了就报错):

| 工具 | 是什么 | 安装命令 |
|---|---|---|
| **Windows 10/11** | 这个项目只支持 Windows(macOS 用姊妹仓) | — |
| **Python 3.11+** | 项目用的语言 | `winget install Python.Python.3.12` |
| **Node.js 16+** | 装 `lark-cli` 用 | `winget install OpenJS.NodeJS.LTS` |
| **NSSM** | 把 daemon 注册成 Windows 服务用 | `winget install NSSM.NSSM` |
| **zellij** | 终端复用器,Claude 跑在它里面 | `winget install zellij-org.zellij` 或 `scoop install zellij` |
| **Claude Code** | 你要遥控的对象 | [claude.com/code](https://claude.com/code) |
| **飞书账号** | 用来扫码登录、收发消息 | 国内版 `feishu.cn` |

> **注**:`lark-cli` 不用预装,`setup.ps1` 会自动 `npm i -g @larksuite/cli`。

## 📥 安装

打开 PowerShell(管理员权限或普通都行,但建议**普通用户**就够,服务装到 user 级别):

```powershell
git clone https://github.com/957662/feishu-bot-claude-windows
cd feishu-bot-claude-windows
pwsh -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup.ps1` 会按顺序做这些:

| 步骤 | 干了啥 |
|---|---|
| 1 | 检查 Python / Node / NSSM / zellij 是否在 PATH,缺一报错退出 |
| 2 | 在仓库根目录建 `.venv\` 虚拟环境 |
| 3 | `pip install -e .[win]` 装项目(含 pywin32) |
| 4 | `npm i -g @larksuite/cli`(如未在 PATH) |
| 5 | 建数据目录 `%USERPROFILE%\.feishu-bot-claude-win\` |
| 6 | 把 `feishu-bot-claude.cmd` shim 写到 `%LOCALAPPDATA%\Programs\feishu-bot-claude-win\` 并加入用户 PATH |
| 7 | 用 NSSM 注册名为 `feishu-bot-claude-win` 的 Windows 服务,设置 auto-start |
| 8 | 启动服务 |

**装完后**,**关掉这个 PowerShell 窗口重开一个**(让新 PATH 生效),然后:

```powershell
feishu-bot-claude ping          # 应该返回 OK { "pong": true }
feishu-bot-claude status        # 应该显示 daemon uptime
```

## 🎯 第一次使用:零到能用全流程

下面用一个真实例子走一遍。假设你要给 `C:\code\my-app` 这个项目绑机器人。

### Step 1:在项目目录启动 zellij + Claude

```powershell
feishu-bot-claude shell --cwd C:\code\my-app --dangerously-skip-permissions
```

> ⚠️ **关于 `--dangerously-skip-permissions`(危险!全权限模式)**
>
> 这是 Claude Code 官方的"**跳过所有权限确认**"开关。加上它之后:
> - Claude **不会再**对任何动作弹"是否允许?"的确认对话框
> - 删文件 / 改文件 / 跑 PowerShell 命令 / 推 git / `iwr ... | iex` 全都**直接执行,无任何拦截**
> - 远程通过飞书发的指令也会被 Claude 直接执行 —— 任何人能给机器人发消息,就能 100% 控制你这台机器
>
> **何时可以加**:
> - ✅ 你在隔离的开发环境 / Sandbox / 临时 VM 里跑
> - ✅ 你完全信任飞书侧的接收人(默认只有你自己)
> - ✅ 你能容忍 Claude 跑飞之后的代价(代码回滚 / 数据恢复)
>
> **何时绝对不要加**:
> - ❌ 在生产机器 / 装着重要数据的工作主力机上
> - ❌ 飞书机器人聊天框可能被其他人看到或操作(没设 `allow_users` 白名单)
> - ❌ 你不知道这个标志会做什么的时候 —— 先去掉它,Claude 会每次跑命令前问你
>
> 想稳一点就把这个标志删掉,正常跑 `feishu-bot-claude shell --cwd C:\code\my-app` 即可;每次危险操作会在 TUI 里弹确认,你可以在飞书的卡片里看到该提示并通过菜单按钮 / 输入 y/n 来批准。

这条命令会:
- **打开一个新的控制台窗口**(因为 Windows 上 zellij 没有 detached 创建模式)
- 在新窗口里跑 `zellij --session claude-my-app -- claude --dangerously-skip-permissions`(如果你加了这个标志)
- 你看到的就是 Claude TUI

> 💡 想关掉窗口但保留 session?**先 `Ctrl+P, D` detach 再关**,session 才会留在后台。直接关窗口会杀掉 Claude。

### Step 2:在 Claude TUI 里输入 `/bot-new <名字>`

```
> /bot-new my-app-bot
```

接下来(整个过程 ~30 秒):
1. **自动弹浏览器**显示飞书 OAuth 授权页
2. 飞书扫码同意,生成新 App
3. 终端依次输出:`✓ App created (cli_xxx)` → `✓ menu pushed` → `✓ binding saved`
4. 提示:`等你给机器人发首条消息以 bootstrap`

### Step 3:打开飞书,找到这个机器人

- 飞书 App → 搜索 → 搜你刚填的名字(`my-app-bot`)
- 点进它的聊天框

### Step 4:给它发任意消息(比如"你好")

这条**首条消息**很特殊:
- 不会传给 Claude
- 只是告诉 daemon:"嘿,这个就是我跟这个机器人的聊天框,记下来"
- daemon 立刻把**当前 Claude 会话的整段历史**渲染成卡片塞进聊天框
- 你能在飞书里看到之前所有对话

> 💡 这一步叫 "bootstrap"(自举)。完成一次后,binding 状态就持久化了,以后服务重启不用再 bootstrap。

### Step 5:开始遥控

发什么消息,Claude 就会收到什么。比如:

> 你:**`帮我把 README 翻译成英文`**
> 🤖 ← ❤️ 已读回执秒贴上
> 🤖 卡片更新:📖 Read README.md → ✏️ Edit README.md → "完成,英文版已写入。"

### Step 6:断开 zellij,Claude 继续后台跑

按 `Ctrl+P, D` detach,然后关窗口。Claude 还在后台跑,daemon 还在镜像。

想看 TUI 再起来一个:

```powershell
feishu-bot-claude shell --cwd C:\code\my-app
# 它会找到已有 session 并 attach 进去
```

## 🔁 日常使用

| 想做啥 | 命令 |
|---|---|
| 看看哪些项目绑了机器人 | `feishu-bot-claude list` |
| 启动某个项目的镜像 | `feishu-bot-claude start --cwd <path>` |
| 停止某个项目的镜像 | `feishu-bot-claude stop --cwd <path>` |
| 进 zellij 看 Claude TUI | `feishu-bot-claude shell --cwd <path>` |
| 看 daemon 活着没 | `feishu-bot-claude ping` |
| 看 daemon 日志 | `Get-Content $env:USERPROFILE\.feishu-bot-claude-win\logs\daemon.err.log -Tail 50 -Wait` |
| 重启服务 | `nssm restart feishu-bot-claude-win` |

## 📚 常用命令大全

### 在 Claude TUI 里(斜杠命令)

| 命令 | 作用 |
|---|---|
| `/bot-new <名字>` | 给当前项目绑一个新机器人 |
| `/bot-list` | 列出所有 binding |
| `/bot-start` | 启动当前项目的镜像 |
| `/bot-stop` | 停止当前项目的镜像 |
| `/bot-config render_style=full` | 调整参数 |
| `/bot-remove <名字>` | 删除 binding(飞书 App 不会被删) |

### 在 PowerShell / cmd 里(CLI)

```powershell
feishu-bot-claude ping                                       # 探活
feishu-bot-claude status                                     # 看版本/uptime
feishu-bot-claude list                                       # 列 binding
feishu-bot-claude bind <name> --cwd <path>                   # 等价 /bot-new
feishu-bot-claude unbind <name>                              # 等价 /bot-remove
feishu-bot-claude start --cwd <path>                         # 启动镜像
feishu-bot-claude stop --cwd <path>                          # 停止镜像
feishu-bot-claude config --cwd <path> render_style=full      # 调参
feishu-bot-claude shell --cwd <path>                         # 起 zellij + Claude
```

## 🔧 服务管理

服务名 **`feishu-bot-claude-win`**,通过 NSSM 管理(也可以用 `sc.exe` 或 Windows 服务管理器):

```powershell
nssm status   feishu-bot-claude-win
nssm start    feishu-bot-claude-win
nssm stop     feishu-bot-claude-win
nssm restart  feishu-bot-claude-win

# 实时看日志
Get-Content $env:USERPROFILE\.feishu-bot-claude-win\logs\daemon.err.log -Tail 50 -Wait
Get-Content $env:USERPROFILE\.feishu-bot-claude-win\logs\daemon.out.log -Tail 50 -Wait

# 改配置后必须 restart
nssm restart feishu-bot-claude-win
```

## 🧹 卸载

```powershell
# 保留 bindings 和历史
pwsh -ExecutionPolicy Bypass -File .\uninstall.ps1

# 连数据目录一起删(凭据除外,凭据管理器里的密钥需要手动删)
pwsh -ExecutionPolicy Bypass -File .\uninstall.ps1 -Purge
```

凭据管理:`控制面板 → 用户账户 → 凭据管理器 → Windows 凭据 → 找到以 "feishu-bot-claude-win:" 开头的项,逐个删除`。

## 🧠 架构详解(进阶)

### 几个核心概念

| 概念 | 解释 |
|---|---|
| **Binding** | 一个 `(项目目录, 飞书 App, zellij session)` 三元组,持久化在 `bindings.toml` |
| **Bootstrap** | 用户给机器人发首条消息触发,daemon 记下 `chat_id` 并把会话历史一次性灌入 |
| **Turn** | Claude 的一轮对话(user 消息 + 所有 assistant 输出),作为一张卡片整体发送 |
| **Outbound** | jsonl 文件 tail → 渲染卡片 → 推送飞书 |
| **Inbound** | 飞书消息 → 注入 zellij → 喂给 Claude |

### 卡片渲染策略

为了不超飞书硬限制(单卡 ≤30 KB、单元素 ≤4 KB、≤50 elements、≤3 tables):

- 一个 turn 攒齐再发,**不按事件刷新**
- 单 element 字符数硬上限 4000,超了加"…(截断 N 字符)…"
- 一张卡 ≤40 elements,超了加"…省略 N 个工具调用/段落…"
- 工具输出预览限制 60 行
- code block 之外的管道符 `|` 自动转义为 `\|`,防止 markdown 表格触发 table 元素限制

### 入站去重

飞书事件总线是 **at-least-once** 投递,同一条消息可能推两次。inbound 维护 LRU(1024 容量)记 `event_id`,重复直接丢。

### 速率限制

飞书 app-bot 接口约 50 req/s。我们用令牌桶限到 **45 req/s, burst 50**。

### 进程模型

```
Windows Service Manager
   └─ NSSM
        └─ python -m feishu_bot_claude_win daemon          (常驻)
             ├─ asyncio task: outbound watcher * N         (每个 binding 一个)
             ├─ asyncio task: inbound consumer * N         (每个 binding 一个)
             └─ asyncio TCP server (127.0.0.1:<动态端口>)  (CLI 通信)
```

### zellij 替代 tmux 的关键命令映射

| tmux(macOS) | zellij(Windows) |
|---|---|
| `tmux has-session -t NAME` | `zellij list-sessions --short` + grep |
| `tmux new-session -d -s NAME` | `subprocess.Popen("zellij --session NAME --", creationflags=CREATE_NEW_CONSOLE)` |
| `tmux send-keys -t NAME -l "text"` | `zellij --session NAME action write-chars "text"` |
| `tmux send-keys -t NAME Enter` | `zellij --session NAME action write 13` |
| `tmux kill-session -t NAME` | `zellij delete-session NAME --force` |

## ❓ 常见问题 FAQ

**Q1: 我没装 NSSM 怎么办?**
A: `winget install NSSM.NSSM`。setup.ps1 没装 NSSM 就过不去。

**Q2: setup.ps1 报 "execution policy" 错?**
A: 用 `pwsh -ExecutionPolicy Bypass -File .\setup.ps1`,Bypass 只对这一次跑生效,不会改你的系统策略。

**Q3: 我能不能不用 Windows 服务,手动跑 daemon?**
A: 可以。`$env:FEISHU_BOT_CLAUDE_DATA_DIR = "$env:USERPROFILE\.feishu-bot-claude-win"; python -m feishu_bot_claude_win daemon` —— 但服务模式更稳。

**Q4: zellij 关掉窗口 Claude 也死了?**
A: 关窗口前先 `Ctrl+P, D` detach。直接关窗 = SIGHUP,zellij 会把内部进程杀掉。

**Q5: 多用户工作站安全吗?**
A: 当前用 TCP loopback,本地其他用户能连。如果你和别人共用一台 Windows,issue 里 +1,我们会加 Named Pipe + DACL 支持。

**Q6: 飞书机器人没收到消息?**
A: 先看日志:`Get-Content $env:USERPROFILE\.feishu-bot-claude-win\logs\daemon.err.log -Tail 50`。常见:bootstrap 没做、服务没起、zellij session 不存在。

**Q7: Claude 收到我两条一样的消息?**
A: 不应该(已加 event_id 去重)。如果发生,贴日志开 issue。

**Q8: 海外飞书 / Lark 怎么办?**
A: `feishu-bot-claude config --cwd <path> domain=https://open.larksuite.com`,然后 `nssm restart feishu-bot-claude-win`。

## 🩺 故障排查

### 服务起不来

```powershell
nssm status feishu-bot-claude-win
Get-Content $env:USERPROFILE\.feishu-bot-claude-win\logs\daemon.err.log -Tail 50
# 看是不是 Python 路径错了:
nssm get feishu-bot-claude-win Application
```

### `feishu-bot-claude` 命令找不到

shim 装好了但 PATH 没生效。**关掉所有 PowerShell 窗口重开一个**。或者直接调:

```powershell
& "$env:LOCALAPPDATA\Programs\feishu-bot-claude-win\feishu-bot-claude.cmd" ping
```

### CLI 报 "daemon not running (no control.port file)"

服务没起,或者 data_dir 不对:

```powershell
nssm restart feishu-bot-claude-win
Start-Sleep 2
Test-Path $env:USERPROFILE\.feishu-bot-claude-win\control.port    # 应该返回 True
```

### zellij 不在 PATH

`winget install zellij-org.zellij`,然后**重开 PowerShell**。或者 `scoop install zellij`(scoop 装的可能装在用户 PATH 下,要重开)。

### 卡片发不出去,飞书返回错误码

| 错误码 | 含义 | 修法 |
|---|---|---|
| `99992402` | uuid > 50 字符 | 升级到最新版,已修 |
| `230025` | 消息体超 30 KB | 改 `render_style=minimal` 或缩短 `max_message_length` |
| `230099 / 11310 element` | 单元素超 4 KB | 同上 |
| `230099 / 11310 table` | 表格数超 3 | 同上;最新版自动转义 `\|` |
| `200861 unsupported tag note` | schema 2.0 不支持 note 标签 | 升级 |
| `11232` | 飞书限流 | 降 `card_throttle_ms` |

## 🧪 开发与测试

```powershell
.venv\Scripts\pytest tests\ -q                  # 跑所有测试
.venv\Scripts\pytest tests\unit -q              # 只跑单测
.venv\Scripts\pytest tests\golden --update-golden -q
```

**177 个测试**,在 macOS / Linux 上也能跑(`win32cred` 会被 mock 掉),保持开发期跨平台。

## License

MIT
