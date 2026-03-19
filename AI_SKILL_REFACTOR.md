# AI Skill 重构总结

## 概述

本次重构将独立的技能模块（weather、news、stock、web_search）统一整合为 AI skill 调用架构，通过 MCP 协议和 API 方式让 AI 直接调用外部服务，同时保持向后兼容。

## 重构内容

### 第一阶段：重构 weather/news/stock 为 AI skill

#### 1. 增强 `ai/skills.py` 模块

新增了统一的工具函数层：

**天气查询**
- `fetch_weather_via_api()` - 通过 WeatherAPI.com 获取天气
- `fetch_weather_via_mcp()` - 通过 MCP 协议调用天气服务
- `format_weather_result()` - 格式化天气数据（支持多语言）

**新闻搜索**
- `fetch_news_via_api()` - 通过 NewsAPI 获取新闻
- `fetch_news_via_search()` - 通过网页搜索获取新闻
- `format_news_result()` - 格式化新闻列表（支持多语言）

**股票查询**
- `fetch_stock_via_search()` - 通过网页搜索获取股票行情
- `format_stock_result()` - 格式化股票结果（支持多语言）

**MCP 支持**
- `call_mcp_tool_wrapper()` - MCP 工具调用封装
- `list_mcp_tools_wrapper()` - 列出 MCP 可用工具

**技能注册**
- `ai_skill_weather()` - 天气技能（AI 原生→WeatherAPI→MCP）
- `ai_skill_news()` - 新闻技能（AI 原生→NewsAPI→网页搜索）
- `ai_skill_stock()` - 股票技能（AI 原生→网页搜索）
- `ai_skill_web_search()` - 网页搜索技能

**提示词生成**
- `get_ai_skills_prompt()` - 生成技能列表提示词
- `get_skills_prompt_section()` - 生成技能列表段落

#### 2. 更新 Python skills 模块

**skills/weather.py**
```python
# 优先使用 AI Skill 模式（支持 MCP/WeatherAPI）
result = execute_ai_skill("weather", {"location": loc}, lang)
if result:
    return result
# 回退到传统模式
```

**skills/news.py**
```python
# 优先使用 AI Skill 模式（支持 NewsAPI/网页搜索）
result = execute_ai_skill("news", {"query": q}, lang)
if result:
    return result
# 回退到传统模式
```

**skills/stock.py**
```python
# 优先使用 AI Skill 模式（支持网页搜索）
result = execute_ai_skill("stock", {"query": query}, lang)
if result:
    return result
# 回退到传统模式
```

**skills/web_search.py**
```python
# 尝试 MCP 搜索工具
mcp_result = call_mcp_tool_wrapper("search", "search", {"query": q})
if mcp_result:
    return mcp_result
# 使用本地 web_search
```

### 第二阶段：整合 web_search 到 AI 原生搜索能力

#### MCP 协议支持

现在可以通过配置 MCP 服务器来扩展搜索能力：

```bash
# .env 配置
MCP_SERVERS=weather,search
MCP_SERVER_WEATHER=python -m ai.mcp_weather_server
MCP_SERVER_SEARCH=npx -y @modelcontextprotocol/server-brave-search
```

#### AI 原生搜索优先

对于支持 `native_web_search` 的 AI 后端（如 Claude CLI、Gemini CLI 等），技能会自动优先使用 AI 的原生搜索能力，无需本地调用。

### 第三阶段：优化 prompt 模板

#### 更新 PROMPT_TEMPLATES

在 `core/config.py` 中更新了多语言 prompt 模板，添加了详细的 AI skill 调用说明：

**中文示例**
```
## 可用 AI 技能
你可以通过以下方式调用技能：
1. task_type="ai_skill", task_payload={"skill": "技能名", "payload": {...}}
2. 直接使用技能名作为 task_type: task_type="技能名", task_payload={...}

技能列表：
- **weather**: 天气查询与播报（支持 MCP/WeatherAPI/网络搜索）
- **news**: 新闻搜索与摘要（支持 NewsAPI/网页搜索/AI 原生搜索）
- **stock**: 查询股票/加密货币行情及分析（支持网页搜索/AI 原生搜索）
- **web_search**: 网页搜索（支持 MCP/本地搜索引擎）

示例：
- 天气：{"task_type": "ai_skill", "task_payload": {"skill": "weather", "payload": {"location": "北京"}}}
- 新闻：{"task_type": "news", "task_payload": {"query": "AI 最新动态"}}
- 股票：{"task_type": "stock", "task_payload": {"query": "TSLA"}}
- 搜索：{"task_type": "web_search", "task_payload": {"query": "OpenAI 发布会"}}
```

#### 动态注入技能列表

`email_daemon.py` 中的 `call_ai()` 函数会自动注入技能列表提示：

```python
from ai.skills import get_ai_skills_prompt
ai_skill_hint = get_ai_skills_prompt(lang or PROMPT_LANG)
if ai_skill_hint:
    tmpl = ai_skill_hint + "\n\n" + tmpl
```

## 使用方式

### 方式 1：AI Skill 模式（推荐）

```json
{
  "task_type": "ai_skill",
  "task_payload": {
    "skill": "weather",
    "payload": {"location": "Tokyo"}
  }
}
```

### 方式 2：直接使用技能名

```json
{
  "task_type": "weather",
  "task_payload": {"location": "Tokyo"}
}
```

### 方式 3：传统模式（向后兼容）

原有的定时任务配置保持不变：

```json
{
  "task_type": "weather",
  "subject": "每天早上天气",
  "schedule_every": "1d",
  "payload": {"location": "Tokyo"}
}
```

## 执行流程

```
用户邮件
    ↓
AI 解析 → 返回 JSON
    ↓
task_type 判断
    ├── "ai_skill" → execute_ai_skill(skill_name, payload)
    │                    ↓
    │               技能注册表查找
    │                    ↓
    │               执行 skill 函数
    │                    ↓
    │               优先级：AI 原生 → API → MCP
    │                    ↓
    │               返回结果
    │
    ├── "weather"/"news"/"stock"/... → Python skill (skills/*.py)
    │                                    ↓
    │                               优先级：AI 原生 → API → MCP
    │
    └── 其他类型 → 原有逻辑
```

## 回退策略（优先级从高到低）

### 天气查询
1. AI 原生搜索（如果 AI 支持 `native_web_search`）
2. WeatherAPI.com（如果配置了 API Key）
3. MCP 天气服务器（如果配置了）

### 新闻搜索
1. AI 原生搜索（如果 AI 支持 `native_web_search`）
2. NewsAPI（如果配置了 API Key）
3. 网页搜索（Google/DuckDuckGo）

### 股票查询
1. AI 原生搜索（如果 AI 支持 `native_web_search`）
2. 网页搜索（Google/DuckDuckGo）

## 配置示例

### .env 配置

```bash
# Weather API（可选，用于天气查询）
WEATHER_API_KEY=your_weather_api_key
WEATHER_DEFAULT_LOCATION=Beijing

# News API（可选，用于新闻搜索）
NEWS_API_KEY=your_news_api_key
NEWS_DEFAULT_QUERY=technology OR AI
NEWS_DEFAULT_PAGE_SIZE=5

# MCP 配置（可选）
MCP_SERVERS=weather
MCP_SERVER_WEATHER=python -m ai.mcp_weather_server

# 搜索配置
WEB_SEARCH_ENGINE=google
SEARCH_RESULTS_COUNT=5
```

## 测试验证

```bash
# 测试 AI Skills 模块
python3 -c "
from ai.skills import list_ai_skills, get_ai_skills_prompt
print('已注册的 AI Skills:')
for sk in list_ai_skills():
    print(f'  - {sk[\"name\"]}: {sk[\"description\"]}')
print()
print('技能提示词:')
print(get_ai_skills_prompt('zh'))
"

# 测试 Python Skills 模块
python3 -c "
from skills.loader import load_all_skills, get_skills_hint
load_all_skills()
print('已加载的 Python Skills:')
print(get_skills_hint('zh'))
"

# 测试向后兼容性
python3 -c "
from tasks.registry import execute_task_logic

# 原有方式
task = {'type': 'weather', 'payload': {'location': 'Tokyo'}}
subject, body = execute_task_logic(task, lang='zh')
print(f'Weather: {subject}')

# AI Skill 方式
task = {'type': 'ai_skill', 'payload': {'skill': 'weather', 'payload': {'location': 'Tokyo'}}}
subject, body = execute_task_logic(task, lang='zh')
print(f'AI Skill Weather: {subject}')
"
```

## 优势

1. **统一架构**: 所有技能通过统一的 `ai.skills` 模块管理
2. **AI 原生优先**: 优先使用 AI 原生联网搜索能力，获取最新数据
3. **灵活回退**: 支持多级回退策略（AI → API → MCP），确保服务可用性
4. **MCP 扩展**: 通过 MCP 协议可轻松扩展新工具
5. **向后兼容**: 现有定时任务无需修改即可正常工作
6. **多语言支持**: 所有提示词和输出支持中/日/英/韩四语

## 后续优化建议

1. 添加更多 MCP 服务器支持（如 GitHub、文件系统、数据库等）
2. 实现技能缓存机制，减少重复 API 调用
3. 添加技能执行日志和监控
4. 支持技能组合和链式调用
5. 实现技能权限和配额管理

## 变更文件清单

- `ai/skills.py` - 核心 AI skill 模块（新增工具函数和注册表）
- `skills/weather.py` - 天气技能（重构为使用 ai.skills）
- `skills/news.py` - 新闻技能（重构为使用 ai.skills）
- `skills/stock.py` - 股票技能（重构为使用 ai.skills）
- `skills/web_search.py` - 网页搜索技能（重构为使用 ai.skills）
- `core/config.py` - 配置模块（更新 prompt 模板）
- `ai/mcp_weather_server.py` - MCP 天气服务器（已有，保持不变）
- `utils/mcp_client.py` - MCP 客户端（已有，保持不变）

## 兼容性说明

- ✅ 现有定时任务配置无需修改
- ✅ 原有 Python skills 继续工作
- ✅ 邮件指令模板保持不变
- ✅ Web UI 和 API 接口不受影响
- ✅ systemd 服务和 Docker 配置无需更改
