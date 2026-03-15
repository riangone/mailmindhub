# MailMind 代码改进与架构演进建议

本文档旨在为 `MailMind` 项目的后续开发提供路线图，重点关注系统的稳定性、可维护性、安全性和 AI 交互体验。

## 1. 架构重构：模块化拆分 (Architecture & Modularization)

当前 `email_daemon.py` 承担了过多的职责，建议通过模块化拆分降低耦合度：

- **`core/`**: 
    - `mail_client.py`: 封装 IMAP 连接池、IDLE 状态管理与异常重连。
    - `mail_sender.py`: 负责 SMTP 发送逻辑与 HTML/Markdown 转换。
- **`ai/`**: 
    - `base.py`: 定义 AI 后端的抽象基类。
    - `providers/`: 存放各厂商（OpenAI, Anthropic, DeepSeek, Local Ollama）的具体实现类。
- **`tasks/`**: 
    - `scheduler.py`: 负责任务的时间调度与触发。
    - `registry.py`: 任务类型（Weather, News, SystemStatus）的注册与分发逻辑。
- **`utils/`**: 
    - `search.py`: 网络搜索工具类。
    - `parser.py`: 邮件指令与自然语言解析逻辑。

## 2. 增强稳定性与网络健壮性 (Stability & Robustness)

IMAP IDLE 模式在长连接环境下极易受网络波动影响：

- **心跳保活机制**: 即使在 IDLE 挂起状态下，也应定时发送 `NOOP` 或重新开启 IDLE 以维持 TCP 连接。
- **指数退避重连 (Exponential Backoff)**: 遭遇网络异常或认证失败时，采用 `2^n` 秒的等待策略进行重试，避免被邮件服务商判定为攻击。
- **并发处理隔离**: 使用 `ThreadPoolExecutor` 处理 AI 任务，确保长耗时任务（如大规模网页检索）不会阻塞主循环的邮件监听。

## 3. 安全性增强 (Security & Verification)

目前仅依赖 `ALLOWED` 发件人白名单，存在被伪造邮件攻击的风险：

- **SPF/DKIM/DMARC 校验**: 引入 `authres` 或相关逻辑，在解析邮件头部时验证发件服务器的合法性。
- **敏感操作二次确认**: 对涉及系统重启、大批量数据删除或高额 Token 消耗的指令，系统应回复确认邮件，并在收到指定确认码后再执行。
- **输入过滤**: 严格转义 AI 输出中的 HTML 标签，防止 XSS 攻击；对 CLI 后端（如 `claude`）的输入进行 Shell 转义，防止命令注入。

## 4. 任务调度与数据持久化 (Persistence & Reliability)

使用 `tasks.json` 存在并发读写风险且难以查询状态：

- **迁移至 SQLite**: 使用轻量级数据库存储任务列表、执行记录和错误日志。
- **任务补执行逻辑**: 在系统启动时识别出因宕机错过的定时任务，根据策略（立即执行或跳过）进行处理。
- **状态快照**: 在 Web UI 中实时展示每个定时任务的“最后一次运行结果”和“下一次预定时间”。

## 5. AI 功能与交互优化 (AI Capabilities & UX)

- **会话上下文管理 (Conversation Context)**: 利用邮件的 `In-Reply-To` 和 `References` 头部建立对话树，使 AI 能够理解“基于上一封邮件进一步修改”这类指令。
- **多级任务进度反馈**: 针对复杂任务（如生成日报），可以先发送“已收到，正在处理”的反馈邮件，处理完成后再发送正式结果。
- **本地 LLM 集成**: 增加对 `Ollama` 或 `vLLM` 的原生支持，提供低成本、高隐私的本地运行模式。
- **增强搜索解析**: 结合 RAG（检索增强生成）理念，对网页搜索结果进行更精细的预清洗和分段，提升 AI 回复的准确度。

## 6. 工程化与运维规范 (Engineering & DevOps)

- **结构化日志**: 使用 `logging` 结合 `json-formatter` 或 `structlog`，使日志更易于被 Web UI 或外部监控系统解析。
- **配置校验**: 使用 `pydantic-settings` 替换简单的 `os.environ.get`，在启动阶段校验 `.env` 变量的完整性和有效性。
- **自动化测试**:
    - 增加对复杂时间解析（如“每周五下午两点”）的单元测试。
    - 增加对 AI 提示词模板的回归测试。
- **Docker 化部署**: 提供官方 Dockerfile 和 docker-compose 模版，实现环境的一键快速部署。
