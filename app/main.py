import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from aiogram.fsm.storage.memory import MemoryStorage

from .config import load_config
from .db import DB
from .handlers import admin, group, student
from .roster import sync_roster
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


async def setup_commands(bot: Bot, cfg) -> None:
    """Telegramdagi «Menyu» tugmasi: o'quvchilarga /start, adminlarga to'liq ro'yxat."""
    await bot.set_my_commands([BotCommand(command="start", description="Boshlash / menyu")], BotCommandScopeDefault())
    admin_cmds = [
        BotCommand(command="vazifa", description="➕ Yangi vazifa qo'shish"),
        BotCommand(command="tekshir", description="📝 Ishlarni tekshirish"),
        BotCommand(command="hisobot", description="📊 Haftalik hisobot"),
        BotCommand(command="oquvchilar", description="👥 O'quvchilar ro'yxati"),
        BotCommand(command="excel", description="📥 Statistika (Excel)"),
        BotCommand(command="zaxira", description="💾 Baza zaxirasi"),
        BotCommand(command="bekor", description="❌ Bekor qilish"),
    ]
    for admin_id in cfg.admin_ids:
        try:
            await bot.set_my_commands(admin_cmds, BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:  # admin hali botga /start bosmagan bo'lishi mumkin
            logging.getLogger(__name__).warning("Admin menyusi o'rnatilmadi (%s): %s", admin_id, e)


async def check_access(bot: Bot, cfg) -> None:
    """Ishga tushganda guruh va kanalga kirish huquqini tekshirib, logga yozadi."""
    log = logging.getLogger("check")
    me = await bot.me()
    for name, chat_id in (("GROUP_ID", cfg.group_id), ("STORAGE_CHANNEL_ID", cfg.storage_channel_id)):
        try:
            chat = await bot.get_chat(chat_id)
            member = await bot.get_chat_member(chat_id, me.id)
            log.info("%s OK: «%s», bot holati: %s", name, chat.title, member.status)
            if name == "STORAGE_CHANNEL_ID" and member.status != "administrator":
                log.error("%s: bot kanalda administrator EMAS — xabar yubora olmaydi!", name)
        except Exception as e:
            log.error("%s=%s ga kirib bo'lmadi: %s", name, chat_id, e)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    db = DB(cfg.db_path, cfg.admin_ids, cfg.database_url)
    await db.init()

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["cfg"] = cfg
    # Admin router birinchi: adminlar uchun /start va buyruqlar shu yerda ushlanadi
    dp.include_router(admin.router)
    dp.include_router(group.router)
    dp.include_router(student.router)

    scheduler = setup_scheduler(bot, db, cfg)
    scheduler.start()

    await check_access(bot, cfg)
    await setup_commands(bot, cfg)
    await start_health_server()
    await bot.delete_webhook(drop_pending_updates=True)
    sync_task = asyncio.create_task(sync_roster(bot, db, cfg))  # ketganlarni ro'yxatdan chiqarish
    # chat_member yangilanishlari avtomatik so'raladi (group.router da handler bor)
    try:
        await dp.start_polling(bot)
        await sync_task
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
