import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config
from .db import DB
from .keyboards import A_REPORT, A_REVIEW, BTN_SUBMIT
from .texts import esc, kv, title
from .timeutil import today, week_start

log = logging.getLogger(__name__)


async def remind_students(bot: Bot, db: DB, cfg: Config) -> None:
    """Bugun hech narsa topshirmagan o'quvchilarga eslatma yuboradi."""
    day = today(cfg.timezone)
    tasks = await db.tasks_for_week(week_start(day).isoformat())
    if not tasks:
        return
    sent = 0
    for s in await db.all_students():
        if await db.has_submission_on(s["user_id"], day):
            continue
        try:
            await bot.send_message(
                s["user_id"],
                f"{title('⏰', 'Eslatma')}\n"
                f"<b>{esc(s['full_name'])}</b>, bugun hali vazifa topshirmadingiz!\n\n"
                f"Menyudan <b>{esc(BTN_SUBMIT)}</b> tugmasini bosib ishingizni yuboring 👇",
            )
            sent += 1
        except TelegramAPIError as e:
            log.warning("Eslatma yuborilmadi (%s): %s", s["user_id"], e)
        await asyncio.sleep(0.05)
    log.info("Eslatmalar yuborildi: %s", sent)


async def week_end_notice(bot: Bot, db: DB, cfg: Config) -> None:
    """Hafta oxirida adminlarga ishlarni tekshirish vaqti kelganini eslatadi."""
    n = await db.pending_count()
    for admin_id in cfg.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"{title('📅', 'Hafta tugadi')}\n"
                f"{kv('📬', 'Tekshirilmagan ishlar', n, code=True)}\n\n"
                f"<b>{esc(A_REVIEW)}</b> — baholashni boshlash\n"
                f"<b>{esc(A_REPORT)}</b> — statistika",
            )
        except TelegramAPIError as e:
            log.warning("Adminga xabar yuborilmadi (%s): %s", admin_id, e)


def setup_scheduler(bot: Bot, db: DB, cfg: Config) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=cfg.timezone)
    sched.add_job(
        remind_students,
        CronTrigger(hour=cfg.reminder_hour, minute=0),
        args=[bot, db, cfg],
        id="daily_reminder",
    )
    sched.add_job(
        week_end_notice,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        args=[bot, db, cfg],
        id="week_end_notice",
    )
    return sched
