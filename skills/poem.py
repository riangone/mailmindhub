from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider


class PoemSkill(BaseSkill):
    name = "poem"
    description = "创作诗歌、对联、歌词等创意文本"
    description_ja = "詩・俳句・歌詞などクリエイティブ創作"
    description_en = "Creative writing: poems, lyrics, verses"
    keywords = ["写诗", "poem", "诗歌", "俳句", "haiku", "lyrics", "歌词", "对联", "詩", "詩を書", "시"]

    def run(self, payload: dict, ai_caller=None) -> str:
        theme = payload.get("theme") or payload.get("prompt") or payload.get("text") or ""
        style = payload.get("style") or ""
        if not theme:
            return "⚠️ Please provide theme in task_payload.prompt"
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)
        style_hint = f"风格：{style}，" if style else ""
        prompt = f'请以「{theme}」为主题，{style_hint}创作一首诗歌/短文，要求有意境、有美感，可以是现代诗或古典诗。'
        return ai.call(prompt) or "⚠️ 创作失败。"


SKILL = PoemSkill()
