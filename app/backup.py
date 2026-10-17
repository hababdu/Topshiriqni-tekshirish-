"""Bazaning to'liq zaxira nusxasi (JSON, gzip) — yopiq kanalga va adminga yuboriladi."""
import gzip
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

from .config import Config
from .db import TABLE_COLS, DB
from .texts import esc, kv, title

log = logging.getLogger(__name__)
FORMAT_VERSION = 1


async def make_backup(db: DB, cfg: Config) -> tuple[bytes, str, dict[str, int]]:
    tables = await db.export_all()
    now = datetime.now(ZoneInfo(cfg.timezone))
    payload = {"version": FORMAT_VERSION, "created": now.isoformat(), "tables": tables}
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    name = f"zaxira_{now:%Y-%m-%d_%H%M}.json.gz"
    return gzip.compress(raw), name, {t: len(r) for t, r in tables.items()}


def parse_backup(data: bytes) -> dict[str, list[dict]]:
    """Zaxira faylini o'qiydi (gzip yoki oddiy JSON) va tekshiradi."""
    try:
        data = gzip.decompress(data)
    except OSError:
        pass  # gzip emas — oddiy JSON bo'lishi mumkin
    try:
        payload = json.loads(data.decode("utf-8"))
        tables = payload["tables"]
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError("Bu zaxira fayli emas yoki buzilgan") from e
    if payload.get("version") != FORMAT_VERSION:
        raise ValueError("Zaxira fayli versiyasi mos kelmaydi")
    for name in TABLE_COLS:
        if not isinstance(tables.get(name), list):
            raise ValueError(f"Zaxirada «{name}» jadvali yo'q")
    return tables


def caption(counts: dict[str, int], name: str) -> str:
    return (
        f"{title('💾', 'Baza zaxirasi')}\n"
        f"{kv('📄', 'Fayl', esc(name))}\n"
        f"{kv('👥', 'Oquvchilar', counts['students'], code=True)}   "
        f"{kv('📋', 'Vazifalar', counts['tasks'], code=True)}   "
        f"{kv('📤', 'Ishlar', counts['submissions'], code=True)}"
    )


async def send_backup(bot: Bot, chat_id: int, db: DB, cfg: Config) -> bool:
    data, name, counts = await make_backup(db, cfg)
    await bot.send_document(chat_id, BufferedInputFile(data, name), caption=caption(counts, name))
    return True


async def scheduled_backup(bot: Bot, db: DB, cfg: Config) -> None:
    """Har kuni yopiq kanalga zaxira yuboradi; muvaffaqiyatsiz bo'lsa adminlarga xabar beradi."""
    try:
        await send_backup(bot, cfg.storage_channel_id, db, cfg)
        log.info("Zaxira kanalga yuborildi")
    except Exception as e:
        log.error("Zaxira yuborilmadi: %s", e)
        for admin_id in cfg.admin_ids:
            try:
                await bot.send_message(admin_id, f"⚠️ <b>Zaxira yuborilmadi:</b> {esc(str(e))[:300]}")
            except TelegramAPIError:
                pass
