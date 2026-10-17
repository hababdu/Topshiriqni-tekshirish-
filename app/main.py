import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .config import load_config
from .db import DB
from .handlers import admin, student
from .scheduler import setup_scheduler


async def start_health_server() -> None:
    """Render (Web Service) port kutadi. PORT berilgan bo'lsa, kichik /health serverini ochamiz."""
    port = os.getenv("PORT")
    if not port:
        return
    from aiohttp import web

    async def ok(_request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(port)).start()


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

    await start_health_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
