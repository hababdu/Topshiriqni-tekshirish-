"""Guruhdagi a'zolarni kuzatib, o'quvchilar ro'yxatini avtomatik yuritadi.

Muhim: bot guruhda ADMINISTRATOR bo'lishi kerak — shunda u chat_member yangilanishlarini
va guruhdagi barcha xabarlarni oladi.
"""
from aiogram import F, Router
from aiogram.types import ChatMemberUpdated, Message, User

from ..config import Config
from ..db import DB
from ..roster import is_active

router = Router()
_seen: set[int] = set()  # har bir xabarda bazaga yozmaslik uchun


async def _remember(db: DB, user: User | None) -> None:
    if user is None or user.is_bot or user.id in _seen:
        return
    await db.upsert_member(user.id, user.full_name, user.username)
    _seen.add(user.id)


@router.chat_member()
async def on_member_change(ev: ChatMemberUpdated, db: DB, cfg: Config) -> None:
    if ev.chat.id != cfg.group_id:
        return
    user = ev.new_chat_member.user
    if user.is_bot:
        return
    if is_active(ev.new_chat_member):
        _seen.discard(user.id)
        await _remember(db, user)
    else:
        _seen.discard(user.id)
        await db.mark_left(user.id)


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def on_group_message(m: Message, db: DB, cfg: Config) -> None:
    if m.chat.id != cfg.group_id:
        return
    for u in m.new_chat_members or []:
        _seen.discard(u.id)
        await _remember(db, u)
    if m.left_chat_member and not m.left_chat_member.is_bot:
        _seen.discard(m.left_chat_member.id)
        await db.mark_left(m.left_chat_member.id)
    await _remember(db, m.from_user)
