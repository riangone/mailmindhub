"""
MCP (Model Context Protocol) client — stdio transport.

Uses subprocess + JSON-RPC 2.0 to talk to local MCP servers.
No third-party libraries required.

Configuration (via .env):
  MCP_SERVERS=filesystem,github          # comma-separated enabled servers
  MCP_SERVER_FILESYSTEM=npx @modelcontextprotocol/server-filesystem /home/user
  MCP_SERVER_GITHUB=npx @modelcontextprotocol/server-github
"""

import json
import os
import shlex
import subprocess
import threading
import time
from typing import Any, Optional
from utils.logger import log

# ── Config ────────────────────────────────────────────────────────────────────

def _get_server_cmd(name: str) -> Optional[list[str]]:
    """Return the shell command for a named MCP server, or None if not configured."""
    key = f"MCP_SERVER_{name.upper()}"
    cmd_str = os.environ.get(key, "").strip()
    if not cmd_str:
        return None
    return shlex.split(cmd_str)

def list_enabled_servers() -> list[str]:
    raw = os.environ.get("MCP_SERVERS", "").strip()
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else []

# ── Low-level JSON-RPC over stdio ─────────────────────────────────────────────

class MCPSession:
    """Single-use session: open → call → close."""

    def __init__(self, server_name: str):
        self.server_name = server_name
        self._proc: Optional[subprocess.Popen] = None
        self._msg_id = 0
        self._lock = threading.Lock()

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def open(self) -> bool:
        cmd = _get_server_cmd(self.server_name)
        if not cmd:
            log.warning(f"MCP: サーバー '{self.server_name}' のコマンドが未設定 (MCP_SERVER_{self.server_name.upper()})")
            return False
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            # Initialize handshake
            resp = self._rpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mailmind", "version": "1.0"},
            })
            if resp is None:
                return False
            # Send initialized notification
            self._notify("notifications/initialized", {})
            return True
        except FileNotFoundError:
            log.warning(f"MCP: サーバーコマンドが見つかりません: {cmd[0]}")
            return False
        except Exception as e:
            log.warning(f"MCP: サーバー起動失敗 ({self.server_name}): {e}")
            return False

    def close(self):
        if self._proc:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None

    def _send(self, obj: dict):
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()

    def _recv(self) -> Optional[dict]:
        try:
            line = self._proc.stdout.readline()
            if not line:
                return None
            return json.loads(line.strip())
        except Exception as e:
            log.debug(f"MCP recv error: {e}")
            return None

    def _rpc(self, method: str, params: dict, timeout: float = 10.0) -> Optional[dict]:
        msg_id = self._next_id()
        self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        # Read until we get a response matching our id (skip notifications), with time-based timeout
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            resp = self._recv()
            if resp is None:
                break
            if resp.get("id") == msg_id:
                return resp
        return None

    def _notify(self, method: str, params: dict):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def list_tools(self) -> list[dict]:
        resp = self._rpc("tools/list", {})
        if resp and "result" in resp:
            return resp["result"].get("tools", [])
        return []

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        resp = self._rpc("tools/call", {"name": tool_name, "arguments": arguments})
        if resp is None:
            return "⚠️ MCP サーバーから応答がありませんでした。"
        if "error" in resp:
            err = resp["error"]
            return f"⚠️ MCP エラー ({err.get('code', '?')}): {err.get('message', str(err))}"
        result = resp.get("result", {})
        content = result.get("content", [])
        parts = []
        for item in content:
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif item.get("type") == "image":
                parts.append("[image]")
            else:
                parts.append(str(item))
        return "\n".join(parts) if parts else str(result)


# ── Public API ────────────────────────────────────────────────────────────────

def call_mcp_tool(server: str, tool: str, args: dict, timeout: int = 30) -> str:
    """
    Call an MCP tool on the named server and return the result as a string.
    Returns an error string on failure.
    """
    if not server:
        return "⚠️ MCP: server が指定されていません。"
    if not tool:
        return "⚠️ MCP: tool が指定されていません。"

    enabled = list_enabled_servers()
    if enabled and server not in enabled:
        return f"⚠️ MCP: サーバー '{server}' は MCP_SERVERS に含まれていません。有効: {', '.join(enabled)}"

    result_box: list[str] = []
    error_box: list[str] = []

    def _run():
        session = MCPSession(server)
        try:
            if not session.open():
                error_box.append(f"⚠️ MCP: サーバー '{server}' の起動に失敗しました。MCP_SERVER_{server.upper()} を確認してください。")
                return
            result = session.call_tool(tool, args or {})
            result_box.append(result)
        except Exception as e:
            error_box.append(f"⚠️ MCP 実行エラー: {e}")
        finally:
            session.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        return f"⚠️ MCP: タイムアウト ({timeout}秒) — サーバー '{server}', ツール '{tool}'"
    if error_box:
        return error_box[0]
    return result_box[0] if result_box else "⚠️ MCP: 結果が返ってきませんでした。"


def list_mcp_tools(server: str, timeout: int = 30) -> str:
    """List available tools on an MCP server, formatted as plain text."""
    result_box: list[str] = []
    error_box: list[str] = []

    def _run():
        session = MCPSession(server)
        try:
            if not session.open():
                error_box.append(f"⚠️ サーバー '{server}' の起動に失敗しました。")
                return
            tools = session.list_tools()
            if not tools:
                result_box.append(f"サーバー '{server}' にツールが見つかりません。")
                return
            lines = [f"## {server} — {len(tools)} ツール\n"]
            for t in tools:
                desc = t.get("description", "")
                lines.append(f"- **{t['name']}**: {desc}")
            result_box.append("\n".join(lines))
        except Exception as e:
            error_box.append(f"⚠️ MCP list_tools エラー: {e}")
        finally:
            session.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        return f"⚠️ MCP list_tools: タイムアウト ({timeout}秒) — サーバー '{server}'"
    if error_box:
        return error_box[0]
    return result_box[0] if result_box else "⚠️ MCP: 結果が返ってきませんでした。"
