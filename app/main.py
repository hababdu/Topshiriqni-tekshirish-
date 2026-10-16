import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .config import load_config
from .db import DB
from .handlers import admin, student
from .scheduler import setup_scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    db = DB(cfg.db_path)
    await db.init()

    bot = Bot(cfg.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["cfg"] = cfg
    # Admin router birinchi: adminlar uchun /start va buyruqlar shu yerda ushlanadi
    dp.include_router(admin.router)
    dp.include_router(student.router)

    scheduler = setup_scheduler(bot, db, cfg)
    scheduler.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
