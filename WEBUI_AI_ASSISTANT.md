# WebUI AI 助手实现文档

## 概述

为 MailMindHub WebUI 添加了侧边滑出式 AI 聊天助手功能，参考了 NetYamlForge 的 AI Assistant 设计。

## 实现的功能

### 1. 后端 API 扩展

**新增端点：**

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat/models` | GET | 获取可用的 AI 模型列表 |
| `/api/chat/{session_id}/stream` | POST | SSE 流式聊天 API |
| `/api/chat/{session_id}/cancel` | POST | 取消正在进行的流式请求 |
| `/chat/sessions-list` | GET | 获取会话列表（HTML 芯片格式） |
| `/chat/{session_id}/messages-html` | GET | 获取消息 HTML |

**特性：**
- ✅ SSE (Server-Sent Events) 流式响应
- ✅ 支持所有 CLI 后端（Claude、Codex、Gemini、Qwen、Copilot）
- ✅ 支持所有 API 后端（OpenAI、Anthropic、Gemini API、通义千问等）
- ✅ 对话历史持久化（SQLite）
- ✅ 多轮对话上下文保持
- ✅ 请求取消功能

### 2. 前端聊天界面

**文件结构：**
```
webui/
├── static/
│   ├── chat.css       # 聊天窗口样式
│   └── chat.js        # 聊天逻辑（原生 JavaScript）
├── templates/
│   ├── chat.html      # 聊天页面
│   └── partials/
│       ├── chat_sessions.html   # 会话列表组件
│       └── chat_messages.html   # 消息列表组件
└── server.py          # 后端 API
```

**UI 特性：**
- ✅ 右侧滑出式聊天面板（点击 Header 中的 💬 图标展开/收起）
- ✅ 消息气泡样式（用户/AI 对话）
- ✅ AI 模型选择器下拉菜单
- ✅ 会话历史芯片列表（顶部横向滚动）
- ✅ Markdown 渲染（使用 marked.js）
- ✅ 代码高亮（使用 highlight.js）
- ✅ 暗色/亮色主题支持
- ✅ 响应式设计（移动端适配）

**交互特性：**
- ✅ Enter 发送，Shift+Enter 换行
- ✅ 输入框自动调整高度
- ✅ 实时打字指示器
- ✅ 加载状态显示
- ✅ 取消正在进行的请求
- ✅ 会话自动重命名（基于第一条消息）
- ✅ 对话历史本地存储（localStorage 保存偏好设置）

### 3. 技术选型

| 组件 | 技术 | 说明 |
|------|------|------|
| 前端框架 | 原生 JavaScript | 无框架依赖，轻量级 |
| CSS | 原生 CSS + CSS Variables | 支持主题切换 |
| 通信 | SSE (Server-Sent Events) | 单向流式响应 |
| Markdown | marked.js (CDN) | 轻量快速 |
| 代码高亮 | highlight.js (CDN) | 支持多种语言 |
| 数据存储 | SQLite | 对话历史持久化 |

### 4. 配置扩展

在 `.env` 中添加（可选）：

```bash
# WebUI AI 助手配置
WEBUI_AI_ENABLED=true
WEBUI_AI_DEFAULT="claude"  # 默认使用的 AI 后端
```

### 5. 安全考虑

- ✅ 会话认证（复用现有 WebUI 密码认证）
- ✅ 速率限制（通过 asyncio 并发控制）
- ✅ 仅允许已配置的 AI 后端
- ✅ 请求超时控制

## 使用方式

### 1. 启动 WebUI

```bash
bash manage.sh webui
# 或
python3 -m uvicorn webui.server:app --host 0.0.0.0 --port 7000
```

### 2. 访问聊天界面

1. 打开浏览器访问 `http://localhost:7000`
2. 登录（如果需要密码）
3. 点击页面右上角的 💬 图标
4. 聊天面板从右侧滑出

### 3. 开始对话

1. 选择 AI 模型（默认 claude）
2. 在输入框中输入问题
3. 按 Enter 或点击发送按钮
4. AI 响应会逐字显示（流式）
5. 可以随时点击取消按钮停止生成

### 4. 管理会话

- **新对话**: 点击面板顶部的 `+` 按钮
- **切换会话**: 点击顶部会话芯片
- **删除会话**: 暂未实现（可在后续版本添加）

## API 响应格式

### SSE 事件类型

```json
// 开始
{"type": "start"}

// Token（流式）
{"type": "token", "content": "AI 响应的部分内容"}

// 完成
{"type": "done", "content": "完整的 AI 响应"}

// 错误
{"type": "error", "message": "错误信息"}

// 取消
{"type": "cancelled"}
```

### 模型列表 API

```json
GET /api/chat/models

{
  "models": [
    {"id": "claude", "name": "Claude CLI", "type": "cli"},
    {"id": "openai", "name": "OpenAI (gpt-4o)", "type": "api"},
    ...
  ]
}
```

## 代码亮点

### 1. 流式响应实现

```python
async def generate():
    cancel_event = asyncio.Event()
    _active_streams[session_id] = {"cancel_flag": cancel_event, "task": asyncio.current_task()}
    
    async for chunk in stream_ai_cli(backend, prompt, cancel_event):
        yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
```

### 2. 前端 SSE 处理

```javascript
fetch(`/api/chat/${sessionId}/stream`, {
    method: 'POST',
    body: JSON.stringify({ message, backend })
})
.then(res => res.body)
.then(reader => {
    const decoder = new TextDecoder();
    const pump = async () => {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            // 处理 SSE 事件...
        }
    };
});
```

### 3. 对话历史上下文

```python
def build_chat_prompt(history: list[dict], current_message: str) -> str:
    """Build prompt with conversation history."""
    context_parts = []
    for msg in history[-10:]:  # Last 10 messages
        role = "User" if msg["role"] == "user" else "Assistant"
        context_parts.append(f"{role}: {msg['content']}")
    
    return f"""Previous conversation:
{context}

User: {current_message}
Assistant:"""
```

## 与 NetYamlForge 对比

| 特性 | NetYamlForge | MailMindHub WebUI |
|------|-------------|-------------------|
| UI 形态 | 右侧滑出面板 | ✅ 右侧滑出面板 |
| 流式响应 | SignalR | ✅ SSE |
| CLI 支持 | Claude, Qwen | ✅ Claude, Codex, Gemini, Qwen, Copilot |
| API 支持 | - | ✅ OpenAI, Anthropic, Gemini 等 |
| 任务管理 | 列表/详情/取消 | ✅ 取消功能 |
| 认证 | OAuth (CLI 管理) | ✅ WebUI 密码认证 |
| Markdown | ✅ | ✅ |
| 代码高亮 | ✅ | ✅ |
| 对话历史 | ✅ | ✅ SQLite 持久化 |
| 多轮上下文 | ✅ | ✅ |

## 后续改进建议

1. **任务管理增强**
   - 查看任务列表
   - 取消/暂停/恢复任务
   - 任务详情查看

2. **文件上传**
   - 支持上传图片/文档
   - AI 分析文件内容

3. **对话导出**
   - 导出为 Markdown
   - 导出为 PDF

4. **快捷指令**
   - 预设 Prompt 模板
   - 常用指令快速输入

5. **性能优化**
   - 消息虚拟滚动（长对话）
   - 会话懒加载

6. **移动端优化**
   - 全屏聊天模式
   - 触摸手势支持

## 已知问题

1. 部分 CLI 工具可能需要交互式终端（如 Copilot），流式输出可能不完整
2. 长对话时消息列表可能较长，建议添加虚拟滚动
3. 会话删除功能暂未实现

## 测试建议

1. **基础功能测试**
   - 发送消息并接收响应
   - 切换 AI 模型
   - 创建新会话
   - 切换会话

2. **流式响应测试**
   - 观察逐字显示效果
   - 测试取消功能

3. **上下文测试**
   - 多轮对话，验证 AI 能理解上下文

4. **压力测试**
   - 同时多个会话
   - 长对话（50+ 消息）

5. **浏览器兼容性**
   - Chrome / Firefox / Safari / Edge

## 总结

成功实现了参考 NetYamlForge 设计的 AI 助手功能，包括：
- ✅ 侧边滑出式 UI
- ✅ SSE 流式响应
- ✅ 多 AI 后端支持
- ✅ 对话历史管理
- ✅ Markdown 和代码高亮
- ✅ 请求取消功能

代码已集成到现有 WebUI 架构中，保持了代码风格和约定的一致性。
