from abc import ABC, abstractmethod


class BaseSkill(ABC):
    """Base class for all MailMindHub skills."""
    name: str = ""
    description: str = ""
    description_ja: str = ""
    description_en: str = ""
    keywords: list = []   # trigger keywords for auto-detection

    @abstractmethod
    def run(self, payload: dict, ai_caller=None) -> str:
        """Execute the skill and return the result as a string."""
        ...
