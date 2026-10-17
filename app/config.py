import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    group_id: int
    storage_channel_id: int
    timezone: str
    reminder_hour: int
    db_path: str
    keepalive_url: str
    keepalive_minutes: int


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f".env faylida {name} ko'rsatilmagan")
    return value


def load_config() -> Config:
    admin_ids = frozenset(
        int(x) for x in _required("ADMIN_IDS").split(",") if x.strip()
    )
    # Render o'zi RENDER_EXTERNAL_URL ni beradi (https://nom.onrender.com)
    keepalive_url = (os.getenv("KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    return Config(
        bot_token=_required("BOT_TOKEN"),
        admin_ids=admin_ids,
        group_id=int(_required("GROUP_ID")),
        storage_channel_id=int(_required("STORAGE_CHANNEL_ID")),
        timezone=os.getenv("TIMEZONE", "Asia/Tashkent"),
        reminder_hour=int(os.getenv("REMINDER_HOUR", "18")),
        db_path=os.getenv("DB_PATH", "data/bot.db"),
        keepalive_url=keepalive_url,
        keepalive_minutes=int(os.getenv("KEEPALIVE_MINUTES", "5")),
    )
