import os
import importlib
from skills import BaseSkill
from utils.logger import log

_registry: dict = {}
_loaded = False


def load_all_skills() -> dict:
    global _registry, _loaded
    skills = {}
    skills_dir = os.path.dirname(__file__)
    for fname in sorted(os.listdir(skills_dir)):
        if fname.startswith('_') or not fname.endswith('.py') or fname == 'loader.py':
            continue
        mod_name = f"skills.{fname[:-3]}"
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, 'SKILL') and isinstance(mod.SKILL, BaseSkill):
                skill = mod.SKILL
                if skill.name:
                    skills[skill.name] = skill
                    log.debug(f"[Skills] Loaded skill: {skill.name}")
        except Exception as e:
            log.warning(f"[Skills] Failed to load {fname}: {e}")
    _registry = skills
    _loaded = True
    return skills


def get_registry() -> dict:
    global _loaded
    if not _loaded:
        load_all_skills()
    return _registry


def get_skill(name: str):
    return get_registry().get(name)


def reload_skills() -> dict:
    global _loaded
    _loaded = False
    return load_all_skills()
