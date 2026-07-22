"""Runtime configuration from environment."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class Config:
    telegram_bot_token: str
    db_path: str

    def __init__(self) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise SystemExit("TELEGRAM_BOT_TOKEN is not set")
        self.telegram_bot_token = token
        self.db_path = os.getenv("PRAYER_DB_PATH", "prayerbot.db").strip()