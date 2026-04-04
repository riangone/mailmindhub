import os
import subprocess
import requests
import logging
from ai.base import AIBase
from utils.logger import log
from core.config import WORKSPACE_DIR

class CLIProvider(AIBase):
    def __init__(self, name: str, backend: dict):
        self.name = name
        self.backend = backend

    def _build_env(self):
        env = os.environ.copy()
        extra_paths = [
            os.path.expanduser("~/.local/bin"),
            os.path.expanduser("~/bin"),
            "/usr/local/bin",
        ]
        nvm_dir = os.path.expanduser("~/.nvm/versions/node")
        if os.path.isdir(nvm_dir):
            for ver in sorted(os.listdir(nvm_dir), reverse=True):
                extra_paths.append(os.path.join(nvm_dir, ver, "bin"))
                break
        current_path = env.get("PATH", "")
        for p in extra_paths:
            if p not in current_path:
                current_path = p + os.pathsep + current_path
        env["PATH"] = current_path
        if self.name == "qwen":
            for key in ["TAVILY_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"]:
                val = os.environ.get(key, "")
                if val:
                    env[key] = val
        return env

    def call(self, prompt: str, progress_cb=None, timeout=None, progress_interval=120, **kwargs) -> str:
        """
        Run CLI AI with streaming output.
        progress_cb(elapsed_seconds: int) — called every progress_interval seconds while running.
        timeout — kill process after this many seconds (None = no limit).
        """
        import threading
        import time as _time

        try:
            env = self._build_env()
            cmd = [self.backend["cmd"]] + self.backend["args"] + [prompt]
            cwd = WORKSPACE_DIR if WORKSPACE_DIR and os.path.isdir(WORKSPACE_DIR) else None
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=cwd,
            )

            stdout_lines = []
            stderr_lines = []

            def _read_stdout():
                for line in proc.stdout:
                    stdout_lines.append(line)

            def _read_stderr():
                for line in proc.stderr:
                    stderr_lines.append(line)

            t_out = threading.Thread(target=_read_stdout, daemon=True)
            t_err = threading.Thread(target=_read_stderr, daemon=True)
            t_out.start()
            t_err.start()

            start = _time.time()
            last_progress = start

            while proc.poll() is None:
                _time.sleep(3)
                elapsed = _time.time() - start
                if timeout and elapsed > timeout:
                    proc.kill()
                    proc.wait()
                    t_out.join(timeout=2)
                    t_err.join(timeout=2)
                    log.error(f"CLI AI 超时（{timeout}秒），进程已终止")
                    return f"AI 出错：执行超时（{int(timeout)} 秒），任务未完成"
                if progress_cb and progress_interval > 0:
                    now = _time.time()
                    if (now - last_progress) >= progress_interval:
                        try:
                            progress_cb(int(elapsed))
                        except Exception:
                            pass
                        last_progress = now

            t_out.join()
            t_err.join()
            result = "".join(stdout_lines).strip()
            if not result and stderr_lines:
                log.warning(f"CLI AI stderr: {''.join(stderr_lines[:5])}")
            return result
        except Exception as e:
            log.error(f"CLI AI 调用失败：{e}")
            return f"AI 出错：{e}"

    def execute_task(self, prompt: str, progress_cb=None, timeout=None, **kwargs) -> str:
        """
        执行任务模式（非交互式）
        
        专门用于编程任务等需要直接执行而不等待用户确认的场景。
        添加额外的执行指令到 prompt 中，让 AI 直接行动。
        """
        import threading
        import time as _time

        # 添加执行指令到 prompt
        exec_prompt = f"""{prompt}

【重要】这是自动执行任务，请直接完成以下要求：
1. 不要询问确认，直接执行任务
2. 如果需要写文件，直接写入
3. 如果需要运行命令，直接执行
4. 在最后简短总结你做了什么
5. 不要输出无关的内容"""

        try:
            env = self._build_env()
            cmd = [self.backend["cmd"]] + self.backend["args"] + [exec_prompt]
            cwd = WORKSPACE_DIR if WORKSPACE_DIR and os.path.isdir(WORKSPACE_DIR) else None
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=cwd,
            )

            stdout_lines = []
            stderr_lines = []

            def _read_stdout():
                for line in proc.stdout:
                    stdout_lines.append(line)

            def _read_stderr():
                for line in proc.stderr:
                    stderr_lines.append(line)

            t_out = threading.Thread(target=_read_stdout, daemon=True)
            t_err = threading.Thread(target=_read_stderr, daemon=True)
            t_out.start()
            t_err.start()

            start = _time.time()
            last_progress = start

            while proc.poll() is None:
                _time.sleep(3)
                elapsed = _time.time() - start
                if timeout and elapsed > timeout:
                    proc.kill()
                    proc.wait()
                    t_out.join(timeout=2)
                    t_err.join(timeout=2)
                    log.error(f"CLI AI 任务执行超时（{timeout}秒），进程已终止")
                    return f"AI 任务执行出错：执行超时（{int(timeout)} 秒），任务未完成"
                if progress_cb and progress_interval > 0:
                    now = _time.time()
                    if (now - last_progress) >= progress_interval:
                        try:
                            progress_cb(int(elapsed))
                        except Exception:
                            pass
                        last_progress = now

            t_out.join()
            t_err.join()
            result = "".join(stdout_lines).strip()
            if not result and stderr_lines:
                log.warning(f"CLI AI 任务执行 stderr: {''.join(stderr_lines[:5])}")
            return result
        except Exception as e:
            log.error(f"CLI AI 任务执行失败：{e}")
            return f"AI 任务执行出错：{e}"

class OpenAIProvider(AIBase):
    def __init__(self, backend: dict):
        self.backend = backend

    def call(self, prompt: str, tools: list = None) -> str:
        try:
            url = self.backend.get("url", "https://api.openai.com/v1/chat/completions")
            headers = {"Authorization": f"Bearer {self.backend['api_key']}", "Content-Type": "application/json"}
            
            data = {
                "model": self.backend["model"],
                "messages": [{"role": "user", "content": prompt}]
            }
            
            # 添加工具支持
            if tools:
                data["tools"] = [tool.to_schema() for tool in tools]
            
            resp = requests.post(url, json=data, headers=headers, timeout=180)
            resp.raise_for_status()
            result = resp.json()
            
            # 检查是否有工具调用
            choice = result["choices"][0]
            if choice.get("finish_reason") == "tool_calls":
                # 处理工具调用
                tool_calls = choice["message"].get("tool_calls", [])
                if tool_calls:
                    from ai.executor import get_tool
                    tool_results = []
                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        tool_args = json.loads(tc["function"]["arguments"])
                        tool = get_tool(tool_name)
                        if tool:
                            result = tool.execute(tool_args)
                            tool_results.append(f"工具 {tool_name} 结果：{result}")
                    
                    # 将工具结果加入对话
                    if tool_results:
                        return self._continue_with_tool_results(prompt, tool_results)
            
            return choice["message"]["content"].strip()
        except Exception as e:
            log.error(f"OpenAI API 调用失败：{e}")
            return f"AI 出错：{e}"
    
    def _continue_with_tool_results(self, original_prompt: str, tool_results: list[str]) -> str:
        """在工具执行后继续对话"""
        try:
            url = self.backend.get("url", "https://api.openai.com/v1/chat/completions")
            headers = {"Authorization": f"Bearer {self.backend['api_key']}", "Content-Type": "application/json"}
            
            messages = [
                {"role": "user", "content": original_prompt},
                {"role": "user", "content": "\n\n".join(tool_results) + "\n\n请根据工具执行结果给出最终回复。"}
            ]
            
            data = {
                "model": self.backend["model"],
                "messages": messages
            }
            
            resp = requests.post(url, json=data, headers=headers, timeout=180)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.error(f"OpenAI API 工具调用继续失败：{e}")
            return f"AI 出错：{e}"

class AnthropicProvider(AIBase):
    def __init__(self, backend: dict):
        self.backend = backend

    def call(self, prompt: str) -> str:
        try:
            headers = {"x-api-key": self.backend["api_key"], "anthropic-version": "2023-06-01", "content-type": "application/json"}
            data = {"model": self.backend["model"], "max_tokens": 8096, "messages": [{"role": "user", "content": prompt}]}
            resp = requests.post("https://api.anthropic.com/v1/messages", json=data, headers=headers, timeout=180)
            resp.raise_for_status()
            return resp.json()["content"][0]["text"].strip()
        except Exception as e:
            log.error(f"Anthropic API 调用失败：{e}")
            return f"AI 出错：{e}"

class GeminiAPIProvider(AIBase):
    def __init__(self, backend: dict):
        self.backend = backend

    def call(self, prompt: str) -> str:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.backend['model']}:generateContent?key={self.backend['api_key']}"
            data = {"contents": [{"parts": [{"text": prompt}]}]}
            resp = requests.post(url, json=data, timeout=180)
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log.error(f"Gemini API 调用失败：{e}")
            return f"AI 出错：{e}"

class QwenAPIProvider(AIBase):
    def __init__(self, backend: dict):
        self.backend = backend

    def call(self, prompt: str) -> str:
        try:
            headers = {"Authorization": f"Bearer {self.backend['api_key']}", "Content-Type": "application/json"}
            data = {"model": self.backend["model"], "messages": [{"role": "user", "content": prompt}]}
            resp = requests.post("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", json=data, headers=headers, timeout=180)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.error(f"Qwen API 调用失败：{e}")
            return f"AI 出错：{e}"


class CohereProvider(AIBase):
    """Cohere API 提供商（支持 Command 系列模型）"""
    def __init__(self, backend: dict):
        self.backend = backend

    def call(self, prompt: str) -> str:
        try:
            headers = {"Authorization": f"Bearer {self.backend['api_key']}", "Content-Type": "application/json"}
            data = {
                "model": self.backend["model"],
                "message": prompt,
                "max_tokens": 4096
            }
            resp = requests.post("https://api.cohere.ai/v2/chat", json=data, headers=headers, timeout=180)
            resp.raise_for_status()
            return resp.json()["message"]["content"][0]["text"].strip()
        except Exception as e:
            log.error(f"Cohere API 调用失败：{e}")
            return f"AI 出错：{e}"


class SparkAPIProvider(AIBase):
    """讯飞星火 API 提供商（使用 OpenAI 兼容格式）"""
    def __init__(self, backend: dict):
        self.backend = backend
        self.api_key = self.backend.get("api_key", "")

    def call(self, prompt: str) -> str:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            data = {"model": self.backend["model"], "messages": [{"role": "user", "content": prompt}]}
            resp = requests.post(
                "https://spark-api-open.xf-yun.com/v1/chat/completions",
                json=data, headers=headers, timeout=180
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.error(f"讯飞星火 API 调用失败：{e}")
            return f"AI 出错：{e}"


class ErnieAPIProvider(AIBase):
    """百度文心一言 API 提供商"""
    def __init__(self, backend: dict):
        self.backend = backend
        self.api_key = self.backend.get("api_key", "")
        self._access_token = None
        self._token_expiry = 0

    def _get_access_token(self) -> str:
        import time
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        
        if ":" in self.api_key:
            api_key, secret_key = self.api_key.split(":", 1)
        else:
            return self.api_key
        
        try:
            resp = requests.post(
                "https://aip.baidubce.com/oauth/2.0/token",
                params={"grant_type": "client_credentials", "client_id": api_key, "client_secret": secret_key},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = time.time() + data.get("expires_in", 2592000) - 600
            return self._access_token
        except Exception as e:
            log.error(f"获取文心一言 access_token 失败：{e}")
            return ""

    def call(self, prompt: str) -> str:
        try:
            access_token = self._get_access_token()
            if not access_token:
                return "AI 出错：无法获取 access_token"
            
            headers = {"Content-Type": "application/json"}
            data = {
                "messages": [{"role": "user", "content": prompt}],
                "max_output_tokens": 4096
            }
            resp = requests.post(
                f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{self.backend['model']}?access_token={access_token}",
                json=data, headers=headers, timeout=180
            )
            resp.raise_for_status()
            return resp.json()["result"].strip()
        except Exception as e:
            log.error(f"文心一言 API 调用失败：{e}")
            return f"AI 出错：{e}"


class OllamaProvider(AIBase):
    """Ollama 本地 LLM 提供商（支持自动检测、模型列表、流式输出）"""

    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, backend: dict):
        self.backend = backend
        self.base_url = backend.get("base_url", self.DEFAULT_BASE_URL).rstrip("/")
        self.model = backend.get("model", "")
        self.stream = backend.get("stream", True)
        if not self.model:
            self.model = self._pick_model()

    def _pick_model(self) -> str:
        """从 Ollama /api/tags 自动选取第一个可用模型"""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            if models:
                return models[0]["name"]
        except Exception as e:
            log.warning(f"Ollama 模型列表获取失败：{e}")
        return "llama3"

    @staticmethod
    def list_models(base_url: str = DEFAULT_BASE_URL) -> list[str]:
        """返回 Ollama 服务上已安装的模型名称列表"""
        try:
            resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception as e:
            log.warning(f"Ollama 模型列表获取失败：{e}")
            return []

    @staticmethod
    def is_available(base_url: str = DEFAULT_BASE_URL) -> bool:
        """检测 Ollama 服务是否正在运行"""
        try:
            resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def call(self, prompt: str) -> str:
        try:
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": self.stream,
            }
            if self.stream:
                resp = requests.post(url, json=payload, stream=True, timeout=300)
                resp.raise_for_status()
                parts = []
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        import json as _json
                        chunk = _json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            parts.append(content)
                        if chunk.get("done"):
                            break
                    except Exception:
                        continue
                return "".join(parts).strip()
            else:
                resp = requests.post(url, json=payload, timeout=300)
                resp.raise_for_status()
                return resp.json()["message"]["content"].strip()
        except Exception as e:
            log.error(f"Ollama API 调用失败：{e}")
            return f"AI 出错：{e}"


def get_ai_provider(ai_name: str, backend: dict) -> AIBase:
    t = backend["type"]
    if t == "cli": return CLIProvider(ai_name, backend)
    if t == "api_openai": return OpenAIProvider(backend)
    if t == "api_anthropic": return AnthropicProvider(backend)
    if t == "api_gemini": return GeminiAPIProvider(backend)
    if t == "api_qwen": return QwenAPIProvider(backend)
    if t == "api_cohere": return CohereProvider(backend)
    if t == "api_spark": return SparkAPIProvider(backend)
    if t == "api_ernie": return ErnieAPIProvider(backend)
    if t == "api_ollama": return OllamaProvider(backend)
    raise ValueError(f"未知 AI 类型：{t}")
