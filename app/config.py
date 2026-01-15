import os
from functools import lru_cache

class Settings:
    DATABASE_URL: str
    WEBHOOK_SECRET: str | None
    LOG_LEVEL: str

    def __init__(self) -> None:
        self.DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
        self.WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

@lru_cache
def get_settings() -> Settings:
    return Settings()
