"""
ai/executor.py — 通用 AI 任务执行框架

核心思想：
1. 将所有 AI 能力统一为「技能 (Skill)」+ 「工具 (Tool)」的组合
2. 为不同 AI 后端提供统一的工具调用接口
3. 支持自动执行模式（无需人工确认）和交互模式（需要确认）
"""

import json
import os
import re
import time
from typing import Any, Callable, Optional

from utils.logger import log
from core.config import WORKSPACE_DIR


# ────────────────────────────────────────────────────────────────
# 工具定义 (Tool Definition)
# ────────────────────────────────────────────────────────────────

class Tool:
    """定义一个可被 AI 调用的工具"""
    
    def __init__(self, name: str, description: str, parameters: dict, func: Callable):
        """
        Args:
            name: 工具名称
            description: 工具描述（会注入到 AI prompt 中）
            parameters: JSON Schema 格式的参数定义
            func: 实际执行的函数，接收 dict 参数返回 str 结果
        """
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
    
    def to_schema(self) -> dict:
        """转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    def to_prompt_hint(self, lang: str = "zh") -> str:
        """转换为注入到 prompt 中的工具描述"""
        if lang == "en":
            return f"- **{self.name}**: {self.description}\n  Parameters: {json.dumps(self.parameters, indent=2)}"
        elif lang == "ja":
            return f"- **{self.name}**: {self.description}\n  パラメータ: {json.dumps(self.parameters, indent=2)}"
        else:
            return f"- **{self.name}**: {self.description}\n  参数: {json.dumps(self.parameters, indent=2)}"
    
    def execute(self, args: dict) -> str:
        """执行工具"""
        try:
            return self.func(args)
        except Exception as e:
            log.error(f"工具执行失败 {self.name}: {e}")
            return f"⚠️ Tool execution failed: {self.name}\nError: {e}"


# ────────────────────────────────────────────────────────────────
# 内置工具注册表
# ────────────────────────────────────────────────────────────────

_registered_tools: dict[str, Tool] = {}


def register_tool(tool: Tool):
    """注册一个工具"""
    _registered_tools[tool.name] = tool
    log.debug(f"🔧 注册工具: {tool.name}")


def get_tool(name: str) -> Optional[Tool]:
    """获取已注册的工具"""
    return _registered_tools.get(name)


def list_tools() -> list[Tool]:
    """列出所有可用工具"""
    return list(_registered_tools.values())


def get_tools_prompt(tools: list[Tool] = None, lang: str = "zh") -> str:
    """生成工具列表提示，注入到 AI prompt 中"""
    if tools is None:
        tools = list(_registered_tools.values())
    
    if not tools:
        return ""
    
    header = {
        "zh": "## 可用工具\n你可以调用以下工具来完成任务。调用方式：在回复中使用 JSON 格式指定工具名和参数。\n",
        "en": "## Available Tools\nYou can call these tools to complete the task. Call format: use JSON to specify tool name and parameters.\n",
        "ja": "## 利用可能なツール\nタスクを完了するために以下のツールを呼び出せます。呼び出し形式：JSON でツール名とパラメータを指定。\n",
        "ko": "## 사용 가능한 도구\n작업을 완료하기 위해 다음 도구를 호출할 수 있습니다. 호출 형식: JSON으로 도구 이름과 매개변수 지정.\n",
    }.get(lang, header["zh"])
    
    parts = [header]
    for tool in tools:
        parts.append(tool.to_prompt_hint(lang))
    
    parts.append({
        "zh": "\n## 工具调用格式\n在回复中使用以下 JSON 格式调用工具：\n```json\n{\"tool\": \"工具名\", \"args\": {\"参数1\": \"值1\", \"参数2\": \"值2\"}}\n```\n可以连续调用多个工具，每次调用后等待结果再继续。",
        "en": "\n## Tool Call Format\nUse the following JSON format to call tools:\n```json\n{\"tool\": \"tool_name\", \"args\": {\"param1\": \"value1\", \"param2\": \"value2\"}}\n```\nYou can call multiple tools in sequence, waiting for results before continuing.",
        "ja": "\n## ツール呼び出し形式\n以下の JSON 形式でツールを呼び出します：\n```json\n{\"tool\": \"tool_name\", \"args\": {\"param1\": \"value1\", \"param2\": \"value2\"}}\n```\n複数のツールを順に呼び出せます。結果を待ってから続行してください。",
        "ko": "\n## 도구 호출 형식\n도구 호출 시 다음 JSON 형식 사용:\n```json\n{\"tool\": \"tool_name\", \"args\": {\"param1\": \"value1\", \"param2\": \"value2\"}}\n```\n여러 도구를 순차적으로 호출할 수 있습니다. 결과를 기다린 후 계속하세요.",
    }.get(lang, ""))
    
    return "\n".join(parts)


# ────────────────────────────────────────────────────────────────
# 默认内置工具
# ────────────────────────────────────────────────────────────────

def _init_default_tools():
    """初始化默认工具"""
    
    # 1. shell_exec - 执行 shell 命令
    from skills.loader import get_skill
    shell_skill = get_skill("shell_exec")
    if shell_skill:
        register_tool(Tool(
            name="shell_exec",
            description="在服务器上执行 shell 命令（受白名单限制）。返回命令输出和退出码。",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "cwd": {"type": "string", "description": "工作目录（可选，必须在 WORKSPACE_DIR 内）"}
                },
                "required": ["command"]
            },
            func=lambda args: shell_skill.run({"command": args.get("command"), "cwd": args.get("cwd")})
        ))
    
    # 2. web_search - 网页搜索
    search_skill = get_skill("web_search")
    if search_skill:
        register_tool(Tool(
            name="web_search",
            description="搜索网页获取最新信息。适用于查询新闻、技术动态、公开数据等。",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "num_results": {"type": "integer", "description": "返回结果数量（默认 5）"}
                },
                "required": ["query"]
            },
            func=lambda args: search_skill.run({"query": args.get("query"), "num_results": args.get("num_results", 5)})
        ))
    
    # 3. code_review - 代码审查
    review_skill = get_skill("code_review")
    if review_skill:
        register_tool(Tool(
            name="code_review",
            description="对代码进行专业审查，指出潜在 Bug、安全隐患、性能问题，并给出改进建议。",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要审查的代码"},
                    "language": {"type": "string", "description": "编程语言（如 python, javascript, go）"}
                },
                "required": ["code"]
            },
            func=lambda args: review_skill.run({
                "code": args.get("code"),
                "lang": args.get("language", "")
            })
        ))
    
    # 4. translate - 翻译
    translate_skill = get_skill("translate")
    if translate_skill:
        register_tool(Tool(
            name="translate",
            description="将文本翻译为指定语言",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要翻译的文本"},
                    "target_lang": {"type": "string", "description": "目标语言（如 English, 中文, 日本語）"}
                },
                "required": ["text", "target_lang"]
            },
            func=lambda args: translate_skill.run({
                "text": args.get("text"),
                "target_lang": args.get("target_lang")
            })
        ))
    
    # 5. summarize - 摘要
    summarize_skill = get_skill("summarize")
    if summarize_skill:
        register_tool(Tool(
            name="summarize",
            description="对文本内容进行摘要精简，提取关键要点",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要摘要的文本"},
                    "lang": {"type": "string", "description": "摘要语言（可选）"}
                },
                "required": ["text"]
            },
            func=lambda args: summarize_skill.run({
                "text": args.get("text"),
                "lang": args.get("lang", "")
            })
        ))


# 模块加载时自动注册
try:
    _init_default_tools()
except Exception as e:
    log.warning(f"初始化默认工具失败: {e}")


# ────────────────────────────────────────────────────────────────
# 任务执行器
# ────────────────────────────────────────────────────────────────

class TaskExecutor:
    """
    通用任务执行器
    
    工作流程：
    1. 解析 AI 回复中的工具调用指令
    2. 依次执行工具
    3. 将结果反馈给 AI（可选，用于多步推理）
    4. 返回最终结果
    """
    
    def __init__(self, ai_provider, tools: list[Tool] = None, max_steps: int = 10):
        """
        Args:
            ai_provider: AI 提供者实例
            tools: 可用工具列表（默认使用所有已注册工具）
            max_steps: 最大执行步骤数（防止无限循环）
        """
        self.ai_provider = ai_provider
        self.tools = tools or list(_registered_tools.values())
        self.max_steps = max_steps
        self.tool_results: list[dict] = []
    
    def execute(self, prompt: str, auto_execute: bool = True, progress_cb=None) -> str:
        """
        执行任务
        
        Args:
            prompt: 任务描述
            auto_execute: 是否自动执行工具（False 则只返回工具调用计划）
            progress_cb: 进度回调函数
        
        Returns:
            执行结果
        """
        if auto_execute:
            return self._execute_with_tools(prompt, progress_cb)
        else:
            return self._plan_only(prompt)
    
    def _plan_only(self, prompt: str) -> str:
        """只生成工具调用计划，不实际执行"""
        tools_hint = get_tools_prompt(self.tools)
        full_prompt = f"{prompt}\n\n{tools_hint}\n\n请给出工具调用计划（JSON 数组），不要执行。"
        
        try:
            return self.ai_provider.call(full_prompt)
        except Exception as e:
            log.error(f"生成工具计划失败: {e}")
            return f"⚠️ 工具计划生成失败: {e}"
    
    def _execute_with_tools(self, prompt: str, progress_cb=None) -> str:
        """执行工具链"""
        tools_hint = get_tools_prompt(self.tools)
        
        # 添加强制执行指令
        exec_instruction = {
            "zh": """
## 执行要求
1. 当需要调用工具时，回复以下 JSON 格式：
```json
{"tool": "工具名", "args": {"参数": "值"}}
```
2. 每次只调用一个工具，等待结果后再继续
3. 如果调用结果不理想，可以调整参数重试
4. 所有工具调用完成后，输出最终回复
5. 如果不需要调用工具，直接回复结果
""",
            "en": """
## Execution Requirements
1. When calling a tool, reply with the following JSON format:
```json
{"tool": "tool_name", "args": {"param": "value"}}
```
2. Call only one tool at a time, wait for the result before continuing
3. If the result is not satisfactory, you can adjust parameters and retry
4. After all tool calls are complete, output the final reply
5. If no tools are needed, reply with the result directly
""",
            "ja": """
## 実行要件
1. ツールを呼び出す際は、以下の JSON 形式で返信してください：
```json
{"tool": "tool_name", "args": {"param": "value"}}
```
2. 一度に1つのツールのみ呼び出し、結果を待ってから続行
3. 結果が不満足な場合はパラメータを調整して再試行可能
4. 全ツール呼び出し完了後、最終返信を出力
5. ツールが不要な場合は直接返信
""",
            "ko": """
## 실행 요구사항
1. 도구 호출 시 다음 JSON 형식으로返信하세요:
```json
{"tool": "tool_name", "args": {"param": "value"}}
```
2. 한 번에 하나의 도구만 호출, 결과를 기다린 후 계속
3. 결과가 만족스럽지 않으면 매개변수 조정 후 재시도 가능
4. 모든 도구 호출 완료 후 최종返信 출력
5. 도구가 필요 없으면 직접返信
""",
        }
        
        # 初始 prompt
        full_prompt = f"{prompt}\n\n{tools_hint}\n\n{exec_instruction}"
        
        step = 0
        conversation = [{"role": "user", "content": full_prompt}]
        final_response = ""
        
        while step < self.max_steps:
            step += 1
            
            # 调用 AI
            ai_response = self._call_ai_with_history(conversation)
            
            if not ai_response:
                final_response = "⚠️ AI 未返回有效回复"
                break
            
            # 尝试解析工具调用
            tool_call = self._parse_tool_call(ai_response)
            
            if tool_call:
                # 执行工具
                tool_name = tool_call.get("tool")
                tool_args = tool_call.get("args", {})
                
                tool = get_tool(tool_name)
                if tool:
                    if progress_cb:
                        progress_cb(f"步骤 {step}: 执行工具 {tool_name}")
                    
                    result = tool.execute(tool_args)
                    self.tool_results.append({
                        "step": step,
                        "tool": tool_name,
                        "args": tool_args,
                        "result": result
                    })
                    
                    # 将结果加入对话历史
                    conversation.append({"role": "assistant", "content": ai_response})
                    conversation.append({
                        "role": "user", 
                        "content": f"工具 {tool_name} 执行结果：\n{result}\n\n请根据结果继续。"
                    })
                else:
                    # 工具不存在
                    conversation.append({"role": "assistant", "content": ai_response})
                    conversation.append({
                        "role": "user",
                        "content": f"⚠️ 工具 '{tool_name}' 不存在。请检查工具列表并重试。"
                    })
            else:
                # 不是工具调用，可能是最终回复
                final_response = ai_response
                break
        
        if step >= self.max_steps:
            final_response += f"\n\n⚠️ 已达到最大执行步数 ({self.max_steps})，任务可能未完成。"
        
        return final_response
    
    def _call_ai_with_history(self, conversation: list[dict]) -> str:
        """调用 AI 并维护对话历史"""
        # 将对话历史拼接成 prompt
        prompt_parts = []
        for msg in conversation[-10:]:  # 最多保留最近 10 条消息
            role = "用户" if msg["role"] == "user" else "助手"
            prompt_parts.append(f"{role}: {msg['content']}")
        
        full_prompt = "\n\n".join(prompt_parts)
        
        try:
            return self.ai_provider.call(full_prompt)
        except Exception as e:
            log.error(f"AI 调用失败: {e}")
            return None
    
    def _parse_tool_call(self, response: str) -> Optional[dict]:
        """从 AI 回复中解析工具调用指令"""
        # 尝试匹配 JSON 格式
        json_patterns = [
            r'```json\s*\n(.*?)\n\s*```',  # ```json ... ```
            r'```\s*\n(.*?)\n\s*```',      # ``` ... ```
            r'\{[^{}]*"tool"[^{}]*\}',      # 直接的 JSON 对象
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                try:
                    json_str = match.group(1) if match.lastindex else match.group(0)
                    data = json.loads(json_str)
                    if "tool" in data:
                        return data
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def get_tool_results_summary(self) -> str:
        """获取所有工具执行结果的摘要"""
        if not self.tool_results:
            return "未调用任何工具"
        
        parts = []
        for result in self.tool_results:
            parts.append(
                f"步骤 {result['step']}: 调用 {result['tool']}\n"
                f"  参数: {json.dumps(result['args'], ensure_ascii=False)}\n"
                f"  结果: {result['result'][:200]}{'...' if len(result['result']) > 200 else ''}"
            )
        
        return "\n\n".join(parts)


# ────────────────────────────────────────────────────────────────
# 便捷函数
# ────────────────────────────────────────────────────────────────

def create_executor(ai_provider, max_steps: int = 10) -> TaskExecutor:
    """创建任务执行器的便捷函数"""
    return TaskExecutor(ai_provider, max_steps=max_steps)


def execute_task_with_tools(ai_provider, prompt: str, max_steps: int = 10, progress_cb=None) -> str:
    """使用工具执行任务的便捷函数"""
    executor = create_executor(ai_provider, max_steps)
    return executor.execute(prompt, auto_execute=True, progress_cb=progress_cb)
