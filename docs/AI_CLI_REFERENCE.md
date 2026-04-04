# AI CLI 调用方式参考文档

本文档详细说明 MailMindHub 项目中各 AI CLI 的调用方式、配置方法和执行流程。

---

## 快速参考表

| AI 名称 | 完整命令 | 环境变量 | Token/Key |
|---------|---------|----------|-----------|
| Claude CLI | `claude --print --dangerously-skip-permissions <prompt>` | `CLAUDE_CMD` | - |
| Codex CLI | `codex exec --skip-git-repo-check --full-auto <prompt>` | `CODEX_CMD` | - |
| Gemini CLI | `gemini -y -p <prompt>` | `GEMINI_CMD` | - |
| Qwen CLI | `qwen --prompt --web-search-default --yolo <prompt>` | `QWEN_CMD` | - |
| Copilot CLI | `copilot <prompt>` | `COPILOT_CMD` | `GITHUB_COPILOT_TOKEN` |

---

## 各 CLI 详细说明

### 1. Claude CLI

**命令格式：**
```bash
claude --print --dangerously-skip-permissions <prompt>
```

**配置项：**
- `CLAUDE_CMD`：自定义 claude 可执行文件路径（可选）

**默认查找路径：**
```
~/.npm-global/bin/claude
~/.local/bin/claude
/usr/local/bin/claude
/usr/bin/claude
```

**安装方式：**
```bash
npm install -g @anthropic-ai/claude-code
```

---

### 2. Codex CLI

**命令格式：**
```bash
codex exec --skip-git-repo-check --full-auto <prompt>
```

**配置项：**
- `CODEX_CMD`：自定义 codex 可执行文件路径（可选）

**默认查找路径：**
```
~/.npm-global/bin/codex
~/.local/bin/codex
/usr/local/bin/codex
/usr/bin/codex
```

**安装方式：**
```bash
npm install -g @openai/codex
```

---

### 3. Gemini CLI

**命令格式：**
```bash
gemini -y -p <prompt>
```

**参数说明：**
- `-y`：自动确认（yes）
- `-p`：打印输出（print）

**配置项：**
- `GEMINI_CMD`：自定义 gemini 可执行文件路径（可选）

**默认查找路径：**
```
~/.npm-global/bin/gemini
~/.local/bin/gemini
/usr/local/bin/gemini
/usr/bin/gemini
```

**安装方式：**
```bash
npm install -g @google/gemini-cli
```

---

### 4. Qwen CLI (通义千问)

**命令格式：**
```bash
qwen --prompt --web-search-default --yolo <prompt>
```

**参数说明：**
- `--prompt`：指定输入 prompt
- `--web-search-default`：启用默认网页搜索
- `--yolo`：自动执行模式（You Only Live Once，无需确认）

**配置项：**
- `QWEN_CMD`：自定义 qwen 可执行文件路径（可选）
- `TAVILY_API_KEY`：Tavily 搜索 API Key（可选）
- `GOOGLE_API_KEY`：Google Search API Key（可选）
- `GOOGLE_SEARCH_ENGINE_ID`：Google CSE ID（可选）

**默认查找路径：**
```
~/.npm-global/bin/qwen
~/.local/bin/qwen
/usr/local/bin/qwen
/usr/bin/qwen
```

**安装方式：**
```bash
npm install -g @anthropics/qwen-cli
```

---

### 5. GitHub Copilot CLI

**命令格式：**
```bash
copilot <prompt>
```

**配置项：**
- `COPILOT_CMD`：自定义 copilot 可执行文件路径（可选）
- `GITHUB_COPILOT_TOKEN`：GitHub Copilot 访问令牌

**默认查找路径：**
```
~/.vscode-server/data/User/globalStorage/github.copilot-chat/copilotCli/copilot
~/.npm-global/bin/copilot
~/.local/bin/copilot
/usr/local/bin/copilot
/usr/bin/copilot
```

**获取 Token：**
1. 安装 VSCode GitHub Copilot 插件
2. 登录后在设置中获取 token
3. 或在 `.env` 中配置 `GITHUB_COPILOT_TOKEN`

---

## CLIProvider 调用流程

所有 CLI 都通过 `CLIProvider.call()` 方法统一调用，核心流程如下：

### 1. 环境变量构建

```python
def _build_env(self):
    env = os.environ.copy()
    
    # 扩展 PATH，包含常见 CLI 路径
    extra_paths = [
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/bin"),
        "/usr/local/bin",
    ]
    
    # 自动检测 NVM Node.js 路径
    nvm_dir = os.path.expanduser("~/.nvm/versions/node")
    if os.path.isdir(nvm_dir):
        for ver in sorted(os.listdir(nvm_dir), reverse=True):
            extra_paths.append(os.path.join(nvm_dir, ver, "bin"))
            break
    
    # 合并 PATH
    current_path = env.get("PATH", "")
    for p in extra_paths:
        if p not in current_path:
            current_path = p + os.pathsep + current_path
    env["PATH"] = current_path
    
    # Qwen CLI 特殊处理：注入搜索 API Key
    if self.name == "qwen":
        for key in ["TAVILY_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"]:
            val = os.environ.get(key, "")
            if val:
                env[key] = val
    
    return env
```

### 2. 命令执行

```python
def call(self, prompt: str, progress_cb=None, timeout=None, progress_interval=120):
    # 构建环境变量
    env = self._build_env()
    
    # 拼接完整命令
    cmd = [self.backend["cmd"]] + self.backend["args"] + [prompt]
    
    # 设置工作目录（Workspace 限制）
    cwd = WORKSPACE_DIR if WORKSPACE_DIR and os.path.isdir(WORKSPACE_DIR) else None
    
    # 启动子进程（流式输出）
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=cwd,
    )
    
    # 流式读取输出
    stdout_lines = []
    stderr_lines = []
    
    # ...（线程读取 stdout/stderr）
    
    # 等待完成（支持超时）
    while proc.poll() is None:
        time.sleep(3)
        elapsed = time.time() - start
        if timeout and elapsed > timeout:
            proc.kill()
            return f"AI 出错：执行超时（{int(timeout)} 秒），任务未完成"
        
        # 进度回调
        if progress_cb and (now - last_progress) >= progress_interval:
            progress_cb(int(elapsed))
    
    # 返回结果
    result = "".join(stdout_lines).strip()
    return result
```

---

## 特性说明

### ✅ 流式输出
实时读取 AI 的 stdout/stderr，避免缓冲区溢出，支持长任务输出。

### ✅ 超时控制
通过 `timeout` 参数限制最大执行时间，超时自动终止进程。

### ✅ 进度回调
通过 `progress_cb` 回调函数通知调用方执行进度（默认每 120 秒）。

### ✅ PATH 自动扩展
自动检测并添加以下路径到环境变量：
- `~/.local/bin`
- `~/bin`
- `/usr/local/bin`
- NVM Node.js 版本目录

### ✅ Workspace 限制
当配置 `WORKSPACE_DIR` 时，CLI 执行的工作目录被限制在该目录内，防止路径穿越。

---

## 配置示例 (.env)

```bash
# 自定义 CLI 路径（可选，通常自动检测）
CLAUDE_CMD="/usr/local/bin/claude"
CODEX_CMD="/home/user/.npm-global/bin/codex"
GEMINI_CMD="/usr/local/bin/gemini"
QWEN_CMD="/usr/local/bin/qwen"
COPILOT_CMD="/home/user/.vscode-server/data/User/globalStorage/github.copilot-chat/copilotCli/copilot"

# Copilot Token
GITHUB_COPILOT_TOKEN="your-copilot-token"

# Qwen 搜索增强（可选）
TAVILY_API_KEY="your-tavily-key"
GOOGLE_API_KEY="your-google-api-key"
GOOGLE_SEARCH_ENGINE_ID="your-cse-id"

# Workspace 限制（推荐生产环境使用）
WORKSPACE_DIR="/home/user/mailmind/workspace"
```

---

## 使用示例

### 命令行方式

```bash
# 使用 Claude CLI
python3 email_daemon.py --mailbox gmail --ai claude

# 使用 Codex CLI
python3 email_daemon.py --mailbox gmail --ai codex

# 使用 Gemini CLI
python3 email_daemon.py --mailbox gmail --ai gemini

# 使用 Qwen CLI（带搜索）
python3 email_daemon.py --mailbox gmail --ai qwen

# 使用 Copilot CLI
python3 email_daemon.py --mailbox gmail --ai copilot
```

### 邮件指令示例

```
# 简单查询
使用 Claude 查询 Python 异步编程最佳实践

# 定时任务（带搜索）
每天 18:00 使用 Qwen 生成日报：天气 Tokyo，新闻 AI，网页检索 OpenAI 发布会
```

---

## 故障排查

### CLI 未找到

**症状：** 日志显示 `CLI AI 调用失败：[Errno 2] No such file or directory`

**解决：**
1. 确认 CLI 已正确安装：`which claude` / `which codex` / ...
2. 在 `.env` 中设置对应 `*_CMD` 环境变量指定完整路径
3. 检查 PATH 是否包含 CLI 安装目录

### 权限问题

**症状：** 日志显示 `Permission denied`

**解决：**
```bash
chmod +x $(which claude)
# 或其他 CLI 路径
```

### Copilot Token 失效

**症状：** Copilot CLI 返回认证错误

**解决：**
1. 在 VSCode 中重新登录 Copilot
2. 更新 `.env` 中的 `GITHUB_COPILOT_TOKEN`
3. 重启守护进程

---

## 相关代码位置

| 模块 | 文件路径 | 说明 |
|------|---------|------|
| CLI 配置 | `core/config.py` | `AI_BACKENDS` 字典，CLI 命令定义 |
| CLI 调用 | `ai/providers/__init__.py` | `CLIProvider` 类实现 |
| 环境变量 | `.env.example` | 配置模板 |
| 入口脚本 | `email_daemon.py` | 主程序入口 |
| 管理脚本 | `manage.sh` | 启动/停止/配置管理 |

---

## 版本信息

- **文档版本**: 1.0
- **最后更新**: 2026-03-27
- **适用版本**: MailMindHub v1.x

---

## 参考链接

- [项目 README](../README.md)
- [QWEN.md](../QWEN.md)
- [CLAUDE.md](../CLAUDE.md)
