# MDLA — Mail-Driven Local Agent

基于邮件指令的 Windows 本地智能代理系统。你只需发一封邮件，即可让运行在本机的 Agent 调用 LLM 与本地工具（命令、文件、邮件、MCP 扩展），并把结果回传给你。

- **零公网暴露**：无需公网 IP、端口映射，以邮箱作为安全信令通道。
- **AI 驱动**：集成 LLM（当前接入通义千问 qwen），自然语言理解意图并编排工具。
- **可配置**：命令白名单、工作目录沙盒、模型参数、轮询间隔等均可通过可视化界面调整。
- **可扩展**：原生支持 MCP（Model Context Protocol）。
- **安全**：白名单认证 + 命令白名单 + 路径沙盒 + 防注入 + 高风险操作确认 + 日志脱敏。

## 架构

```
┌─────────────┐   IMAP/SMTP    ┌──────────────┐
│  你的邮箱     │ ◄────────────► │  Agent (Python│
│ (发指令)      │               │  mail_listener│
└─────────────┘               │  agent_core   │
                               │  tool_executor│
┌─────────────┐  命名管道 IPC    │  mcp_client   │
│  GUI (CTk)   │ ◄────────────► └──────────────┘
└─────────────┘
```

- **Agent（`agent/`）**：Python 3.11+，负责邮件监听、LLM 调度、工具执行、MCP 管理、日志与 IPC。
- **GUI（`gui/`）**：CustomTkinter 桌面界面，提供状态监控、配置编辑、历史问答与日志查看。

## 目录结构

```
mailagent/
├── Config/                 # 配置文件（JSON），secrets.json 不提交
│   ├── email.json
│   ├── whitelist.json
│   ├── llm.json
│   ├── permissions.json
│   ├── mcp_servers.json
│   ├── system.json
│   └── secrets.json.example
├── agent/                  # Agent 源码
│   ├── main.py             # 入口
│   ├── agent_core.py       # LLM 调度、防注入、Token 预算、高风险确认
│   ├── mail_listener.py    # IMAP 监听（白名单+限频，UID 水位去重）
│   ├── mail_sender.py      # SMTP 发送（附件 RFC 2047 中文文件名）
│   ├── tool_executor.py    # 命令白名单、路径沙盒、文件操作
│   ├── mcp_client.py       # MCP stdio 客户端
│   ├── config_loader.py    # 配置加载、热加载、版本迁移
│   ├── logger.py           # 结构化 JSONL 日志（脱敏、轮转）
│   ├── history.py          # 问答历史（按天分文件）
│   ├── ipc_server.py       # 命名管道服务端（心跳/指令）
│   ├── secrets.py          # DPAPI 加解密
│   └── requirements.txt
├── gui/                    # CustomTkinter 图形界面
│   ├── app.py              # 主窗口与侧边栏导航
│   ├── store.py            # 配置读写
│   ├── agent_manager.py    # Agent 进程管理 + IPC
│   └── pages/              # 主页/邮件/白名单/大模型/权限/系统/MCP/历史/日志
└── Logs/                   # 运行日志与历史（不提交）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r agent/requirements.txt
```

依赖：`openai`、`pywin32`、`customtkinter`、`tkcalendar`。

### 2. 配置

在 `Config/` 下填写配置文件，并将 `secrets.json.example` 复制为 `secrets.json`，填入：

| 字段 | 说明 |
| :--- | :--- |
| `email_password` / `smtp_password` | 邮箱 IMAP/SMTP 授权码 |
| `access_token` | 访问令牌（白名单命中时可免令牌） |
| `api_keys` | 各 LLM 提供商的 API Key |

### 3. 启动

```bash
# 启动图形界面
python gui/app.py

# 或直接以无界面方式启动 Agent
python agent/main.py
```

### 4. 发指令

从白名单邮箱向 Agent 绑定的邮箱发邮件，正文即自然语言指令，例如：

```
请列出桌面上的文件
把桌面上的个人简历.pdf发给我
执行命令 systeminfo
```

Agent 收到后调用 LLM + 工具执行，并把结果邮件回复给你。

## 核心配置说明

| 文件 | 关键字段 |
| :--- | :--- |
| `email.json` | 服务器/端口、轮询间隔、附件限制、临时目录 |
| `whitelist.json` | 允许/禁用的发件人 |
| `llm.json` | 提供商、模型、Token 预算、系统提示词 |
| `permissions.json` | 命令白名单、工作目录沙盒、高风险操作、限频 |
| `mcp_servers.json` | MCP 服务器列表 |
| `system.json` | 主题、日志级别、语言 |

## 安全说明

- 发件人白名单认证；高风险操作（默认「删除」）需邮件 `CONFIRM` 二次确认。
- 命令白名单 + 路径沙盒 + 硬性禁用危险命令。
- 敏感字段（密码/Token/API Key）在日志中自动脱敏；`secrets.json` 不入库。