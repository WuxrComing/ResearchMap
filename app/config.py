import os
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-v4-flash"
    DATABASE_PATH: str = str(
        Path(__file__).parent.parent / "storage" / "research_map.db"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Fix empty-string overrides from .env
        if not self.DEEPSEEK_API_KEY:
            self.DEEPSEEK_API_KEY = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
        if not self.DEEPSEEK_BASE_URL:
            self.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
        if not self.LLM_MODEL:
            raw = os.getenv("ANTHROPIC_MODEL", "deepseek-v4-flash")
            # Strip context-window suffix like "[1m]"
            import re
            self.LLM_MODEL = re.sub(r"\[.*\]", "", raw)


settings = Settings()
