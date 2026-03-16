import os
import subprocess
import requests
import logging
from ai.base import AIBase
from utils.logger import log

class CLIProvider(AIBase):
    def __init__(self, name: str, backend: dict):
        self.name = name
        self.backend = backend

    def call(self, prompt: str) -> str:
        try:
            env = os.environ.copy()
            # 补充常见 CLI 工具安装路径，防止守护进程在精简 PATH 环境中找不到命令
            extra_paths = [
                os.path.expanduser("~/.local/bin"),
                os.path.expanduser("~/bin"),
                "/usr/local/bin",
            ]
            # 补充 nvm 管理的 node bin 目录
            nvm_dir = os.path.expanduser("~/.nvm/versions/node")
            if os.path.isdir(nvm_dir):
                for ver in sorted(os.listdir(nvm_dir), reverse=True):
                    extra_paths.append(os.path.join(nvm_dir, ver, "bin"))
                    break  # 只取最新版本
            current_path = env.get("PATH", "")
            for p in extra_paths:
                if p not in current_path:
                    current_path = p + os.pathsep + current_path
            env["PATH"] = current_path

            if self.name == "qwen":
                for key in ["TAVILY_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"]:
                    val = os.environ.get(key, "")
                    if val: env[key] = val

            return subprocess.run(
                [self.backend["cmd"]] + self.backend["args"] + [prompt],
                capture_output=True,
                text=True,
                timeout=180,
                env=env
            ).stdout.strip()
        except Exception as e:
            log.error(f"CLI AI 调用失败：{e}")
            return f"AI 出错：{e}"

class OpenAIProvider(AIBase):
    def __init__(self, backend: dict):
        self.backend = backend

    def call(self, prompt: str) -> str:
        try:
            url = self.backend.get("url", "https://api.openai.com/v1/chat/completions")
            headers = {"Authorization": f"Bearer {self.backend['api_key']}", "Content-Type": "application/json"}
            data = {"model": self.backend["model"], "messages": [{"role": "user", "content": prompt}]}
            resp = requests.post(url, json=data, headers=headers, timeout=180)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.error(f"OpenAI API 调用失败：{e}")
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
    raise ValueError(f"未知 AI 类型：{t}")
