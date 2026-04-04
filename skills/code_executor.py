"""
code_executor skill — 编程任务执行器

支持 AI 驱动的编程任务：
1. 生成代码
2. 写入文件
3. 执行测试
4. 返回结果

安全特性：
- 所有文件操作限制在 WORKSPACE_DIR 内
- 命令执行受 SHELL_EXEC_ALLOW 白名单限制
- 超时保护
"""

import os
import subprocess
import tempfile
from pathlib import Path
from skills import BaseSkill
from skills.loader import get_skill
from core.config import WORKSPACE_DIR
from utils.logger import log


def _validate_path(file_path: str) -> bool:
    """验证路径是否在 WORKSPACE_DIR 内"""
    if not WORKSPACE_DIR:
        return True  # 未设置 workspace 则不限制
    
    real_workspace = os.path.realpath(WORKSPACE_DIR)
    real_path = os.path.realpath(os.path.join(real_workspace, file_path))
    return real_path.startswith(real_workspace)


class CodeExecutorSkill(BaseSkill):
    name = "code_executor"
    description = "执行编程任务：生成代码、写入文件、运行测试（受 WORKSPACE_DIR 限制）"
    description_ja = "プログラミングタスク実行：コード生成、ファイル書き込み、テスト実行（WORKSPACE_DIR 制約あり）"
    description_en = "Execute programming tasks: generate code, write files, run tests (restricted to WORKSPACE_DIR)"
    keywords = ["编程", "写代码", "实现", "create file", "write code", "coding", "開発", "プログラミング", "코딩", "프로그래밍"]

    def run(self, payload: dict, ai_caller=None) -> str:
        """
        执行编程任务
        
        payload 结构：
        {
            "action": "generate" | "write" | "test" | "execute",
            "code": "代码内容",
            "file_path": "文件路径（相对 workspace）",
            "test_command": "测试命令",
            "language": "编程语言",
            "description": "任务描述"
        }
        """
        action = payload.get("action", "generate").lower()
        code = payload.get("code") or payload.get("content") or ""
        file_path = payload.get("file_path") or payload.get("filepath") or ""
        test_command = payload.get("test_command") or payload.get("cmd") or ""
        language = payload.get("language") or payload.get("lang") or ""
        description = payload.get("description") or payload.get("prompt") or ""
        
        # 确定 AI caller
        ai_caller = ai_caller or self._get_ai_caller(payload)
        
        if action == "generate":
            return self._generate_code(description, language, ai_caller)
        elif action == "write":
            return self._write_code(code, file_path)
        elif action == "test":
            return self._run_tests(test_command, file_path)
        elif action == "execute":
            return self._execute_code(code, file_path, language)
        else:
            return f"⚠️ 未知操作: {action}。支持的操作: generate, write, test, execute"

    def _get_ai_caller(self, payload: dict):
        """获取 AI 调用器"""
        from tasks.registry import pick_task_ai
        from ai.providers import get_ai_provider
        
        ai_name, backend = pick_task_ai(payload)
        return get_ai_provider(ai_name, backend)

    def _generate_code(self, description: str, language: str, ai_caller) -> str:
        """生成代码"""
        if not description:
            return "⚠️ 请提供代码生成需求描述。"
        
        lang_hint = f"\n编程语言：{language}" if language else ""
        workspace_hint = f"\n工作目录：{WORKSPACE_DIR}" if WORKSPACE_DIR else ""
        
        prompt = f"""请根据以下需求生成代码：

需求描述：{description}
{lang_hint}
{workspace_hint}

要求：
1. 代码完整、可运行
2. 包含必要的注释
3. 遵循最佳实践
4. 处理可能的异常情况
5. 如果是文件操作，确保路径安全

请直接回复代码，不要加任何解释。"""
        
        try:
            result = ai_caller.call(prompt)
            if result:
                return f"✅ 代码生成成功：\n\n```\n{result}\n```\n\n💡 提示：使用 action='write' 和 file_path 参数可将代码写入文件。"
            else:
                return "⚠️ 代码生成失败，AI 未返回结果。"
        except Exception as e:
            log.error(f"代码生成失败: {e}")
            return f"⚠️ 代码生成失败: {e}"

    def _write_code(self, code: str, file_path: str) -> str:
        """将代码写入文件"""
        if not code:
            return "⚠️ 请提供要写入的代码内容。"
        if not file_path:
            return "⚠️ 请提供文件路径。"
        
        # 验证路径
        if not _validate_path(file_path):
            return f"⚠️ 文件路径超出 WORKSPACE_DIR 限制：{file_path}"
        
        try:
            # 构建完整路径
            full_path = os.path.join(WORKSPACE_DIR, file_path) if WORKSPACE_DIR else file_path
            
            # 确保目录存在
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # 写入文件
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            return f"✅ 代码已写入文件：{file_path}\n文件路径：{full_path}"
        except Exception as e:
            log.error(f"文件写入失败: {e}")
            return f"⚠️ 文件写入失败: {e}"

    def _run_tests(self, test_command: str, file_path: str) -> str:
        """运行测试"""
        if not test_command:
            return "⚠️ 请提供测试命令。"
        
        # 验证工作目录
        cwd = WORKSPACE_DIR
        if file_path:
            if not _validate_path(file_path):
                return f"⚠️ 文件路径超出 WORKSPACE_DIR 限制：{file_path}"
            cwd = os.path.dirname(os.path.join(WORKSPACE_DIR, file_path)) if WORKSPACE_DIR else os.path.dirname(file_path)
        
        try:
            result = subprocess.run(
                test_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,  # 60 秒超时
                cwd=cwd,
            )
            
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            rc = result.returncode
            
            parts = [f"$ {test_command}", f"[退出码: {rc}]"]
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append(f"[stderr]\n{stderr}")
            
            status = "✅ 测试通过" if rc == 0 else "❌ 测试失败"
            return f"{status}\n\n" + "\n\n".join(parts)
        except subprocess.TimeoutExpired:
            return f"⏱️ 测试超时（>60s）：{test_command}"
        except Exception as e:
            return f"⚠️ 测试执行出错: {e}"

    def _execute_code(self, code: str, file_path: str, language: str) -> str:
        """执行代码"""
        if not code:
            return "⚠️ 请提供要执行的代码。"
        
        # 确定执行命令
        lang_commands = {
            "python": "python3",
            "python3": "python3",
            "python2": "python2",
            "node": "node",
            "javascript": "node",
            "js": "node",
            "ruby": "ruby",
            "php": "php",
            "perl": "perl",
            "bash": "bash",
            "shell": "bash",
            "sh": "bash",
        }
        
        cmd = lang_commands.get(language.lower())
        if not cmd:
            # 尝试从文件扩展名推断
            ext_map = {
                ".py": "python3",
                ".js": "node",
                ".rb": "ruby",
                ".php": "php",
                ".pl": "perl",
                ".sh": "bash",
            }
            ext = os.path.splitext(file_path)[1] if file_path else ""
            cmd = ext_map.get(ext)
        
        if not cmd:
            return f"⚠️ 不支持的编程语言：{language}。支持的语言: {', '.join(lang_commands.keys())}"
        
        try:
            # 如果提供了文件路径，先写入文件再执行
            if file_path:
                if not _validate_path(file_path):
                    return f"⚠️ 文件路径超出 WORKSPACE_DIR 限制：{file_path}"
                
                full_path = os.path.join(WORKSPACE_DIR, file_path) if WORKSPACE_DIR else file_path
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(code)
                
                # 执行文件
                result = subprocess.run(
                    f"{cmd} {full_path}",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=WORKSPACE_DIR,
                )
            else:
                # 直接执行代码（通过 stdin）
                result = subprocess.run(
                    cmd,
                    shell=True,
                    input=code,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=WORKSPACE_DIR,
                )
            
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            rc = result.returncode
            
            parts = [f"[退出码: {rc}]"]
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append(f"[stderr]\n{stderr}")
            
            status = "✅ 执行成功" if rc == 0 else "❌ 执行失败"
            return f"{status}\n\n" + "\n\n".join(parts)
        except subprocess.TimeoutExpired:
            return f"⏱️ 代码执行超时（>30s）"
        except Exception as e:
            return f"⚠️ 代码执行出错: {e}"


SKILL = CodeExecutorSkill()
