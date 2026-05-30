import importlib
from ai.base import AIBase
from utils.logger import log

def get_ai_provider(ai_name: str, backend: dict) -> AIBase:
    """
    根据配置动态加载 AI 提供商类。
    支持类型映射：
    - 'cli' -> ai.providers.cli.CLIProvider
    - 'api_openai' -> ai.providers.openai.OpenAIProvider
    - 'api_anthropic' -> ai.providers.anthropic.AnthropicProvider
    - 'api_antigravity' -> ai.providers.antigravity.AntigravityAPIProvider
    """
    provider_type = backend.get("type", "")
    
    try:
        if provider_type == "cli":
            from ai.providers.cli import CLIProvider
            return CLIProvider(ai_name, backend)
        
        # 映射表：类型关键词 -> (模块名, 类名)
        type_map = {
            "api_openai": ("openai", "OpenAIProvider"),
            "api_qwen": ("openai", "OpenAIProvider"), # 兼容 OpenAI
            "api_deepseek": ("openai", "OpenAIProvider"), # 兼容 OpenAI
            "api_anthropic": ("anthropic", "AnthropicProvider"),
            "api_antigravity": ("antigravity", "AntigravityAPIProvider"),
            "api_ollama": ("ollama", "OllamaProvider"),
            "api_spark": ("spark", "SparkAPIProvider"),
            "api_ernie": ("ernie", "ErnieAPIProvider"),
            "api_cohere": ("cohere", "CohereProvider"),
        }
        
        if provider_type in type_map:
            module_name, class_name = type_map[provider_type]
            module = importlib.import_module(f"ai.providers.{module_name}")
            provider_class = getattr(module, class_name)
            return provider_class(backend)
            
        raise ValueError(f"不支持的 AI 后端类型：{provider_type}")
        
    except ImportError as e:
        log.error(f"无法加载 AI 提供商模块 {provider_type}: {e}")
        raise
    except AttributeError as e:
        log.error(f"在模块中找不到提供商类 {provider_type}: {e}")
        raise
