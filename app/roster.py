"""O'quvchilar ro'yxati = guruh a'zolari.

Telegram Bot API guruh a'zolarining to'liq ro'yxatini bermaydi, shuning uchun bot a'zolarni
o'zi yig'adi: guruhga qo'shilganda/chiqqanda (chat_member), guruhda yozganda va botga /start
bosganda. Ketganlar avtomatik ro'yxatdan chiqariladi.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from .config import Config
from .db import DB

log = logging.getLogger(__name__)


def is_active(member) -> bool:
    if member.status in ("member", "administrator", "creator"):
        return True
    return member.status == "restricted" and getattr(member, "is_member", False)


async def in_group(bot: Bot, group_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(group_id, user_id)
    except TelegramAPIError:
        return False
    return is_active(member)


async def sync_roster(bot: Bot, db: DB, cfg: Config) -> None:
    """Ro'yxatdagilarni guruh bilan solishtiradi: guruhdan chiqib ketganlarni olib tashlaydi."""
    removed = 0
    for s in await db.all_students():
        try:
            member = await bot.get_chat_member(cfg.group_id, s["user_id"])
        except TelegramAPIError as e:
            log.warning("A'zolik tekshirilmadi (%s): %s", s["user_id"], e)
            continue
        if not is_active(member):
            await db.mark_left(s["user_id"])
            removed += 1
        await asyncio.sleep(0.05)
    log.info("Ro'yxat sinxronlandi, chiqarilganlar: %s", removed)
