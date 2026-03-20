"""
shell_exec skill — Execute sandboxed shell commands and return output.

Security model:
  - SHELL_EXEC_ALLOW  env var: comma-separated command prefixes that are permitted.
                      Empty → all commands denied. "*" → all allowed (not recommended).
  - SHELL_EXEC_TIMEOUT env var: per-command timeout in seconds (default: 30).
  - Working directory is restricted to WORKSPACE_DIR when set.
"""

import os
import subprocess
from skills import BaseSkill

_ALLOW_ENV = os.environ.get("SHELL_EXEC_ALLOW", "")
_TIMEOUT    = int(os.environ.get("SHELL_EXEC_TIMEOUT", "30"))
_WORKSPACE  = os.environ.get("WORKSPACE_DIR", "")


def _allowed(command: str) -> bool:
    if _ALLOW_ENV.strip() == "*":
        return True
    prefixes = [p.strip() for p in _ALLOW_ENV.split(",") if p.strip()]
    if not prefixes:
        return False
    cmd_head = command.strip().split()[0] if command.strip() else ""
    return any(cmd_head == p or cmd_head.endswith(f"/{p}") for p in prefixes)


class ShellExecSkill(BaseSkill):
    name = "shell_exec"
    description = "在服务器上执行 shell 命令并返回输出（受 SHELL_EXEC_ALLOW 白名单限制）"
    description_ja = "サーバーでシェルコマンドを実行して出力を返す（SHELL_EXEC_ALLOW ホワイトリストによる制限あり）"
    description_en = "Execute a shell command on the server and return its output (restricted by SHELL_EXEC_ALLOW allowlist)"
    keywords = ["shell", "bash", "执行命令", "run command", "コマンド実行", "terminal", "script"]

    def run(self, payload: dict, ai_caller=None) -> str:
        command = (payload.get("command") or payload.get("cmd") or "").strip()
        if not command:
            return "⚠️ task_payload 中未提供 command 字段。"

        if not _allowed(command):
            allowed_list = _ALLOW_ENV or "(empty — all denied)"
            return (
                f"⛔ 命令被拒绝：{command!r}\n"
                f"当前白名单：{allowed_list}\n"
                f"请在 .env 中设置 SHELL_EXEC_ALLOW=<cmd1,cmd2,...> 或 SHELL_EXEC_ALLOW=* 以允许执行。"
            )

        cwd = payload.get("cwd") or _WORKSPACE or None
        if cwd:
            # Prevent path traversal out of workspace
            if _WORKSPACE:
                real_cwd = os.path.realpath(cwd)
                real_ws  = os.path.realpath(_WORKSPACE)
                if not real_cwd.startswith(real_ws):
                    return f"⛔ 工作目录 {cwd!r} 超出 WORKSPACE_DIR 限制。"
            if not os.path.isdir(cwd):
                return f"⚠️ 工作目录不存在：{cwd}"

        timeout = int(payload.get("timeout") or _TIMEOUT)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            rc     = result.returncode

            parts = [f"$ {command}", f"[exit code: {rc}]"]
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append(f"[stderr]\n{stderr}")
            return "\n".join(parts)

        except subprocess.TimeoutExpired:
            return f"⏱️ 命令超时（>{timeout}s）：{command}"
        except Exception as e:
            return f"⚠️ 执行出错：{e}"


SKILL = ShellExecSkill()
