from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, TelegramObject

from ..charts import weekly_chart
from ..config import Config
from ..db import DB
from ..keyboards import (
    A_CANCEL,
    A_REPORT,
    A_REPORT_PREV,
    A_REVIEW,
    A_STUDENTS,
    A_TASK,
    admin_kb,
    grade_kb,
    report_kb,
)
from ..timeutil import today, week_range, week_start


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, cfg: Config) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in cfg.admin_ids)


router = Router()
router.message.filter(F.chat.type == "private", IsAdmin())
router.callback_query.filter(IsAdmin())


ADMIN_BTNS = {A_TASK, A_REVIEW, A_REPORT, A_REPORT_PREV, A_STUDENTS, A_CANCEL}


class NewTask(StatesGroup):
    title = State()
    desc = State()


HELP = (
    "👨‍🏫 Admin paneli\n\n"
    "/vazifa — yangi vazifa qo'shish (guruhga e'lon qilinadi)\n"
    "/tekshir — topshirilgan ishlarni ko'rib baholash\n"
    "/hisobot — shu haftalik statistika va diagramma\n"
    "/hisobot 1 — o'tgan hafta hisoboti\n"
    "/oquvchilar — ro'yxatdan o'tgan o'quvchilar\n"
    "/bekor — joriy amalni bekor qilish"
)


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(HELP, reply_markup=admin_kb())


@router.message(Command("bekor"))
@router.message(F.text == A_CANCEL)
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Bekor qilindi.", reply_markup=admin_kb())


# ---------- vazifa qo'shish ----------
@router.message(Command("vazifa"))
@router.message(F.text == A_TASK)
async def new_task(m: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewTask.title)
    await m.answer("Vazifa nomini yozing:")


@router.message(NewTask.title, F.text, ~F.text.in_(ADMIN_BTNS))
async def task_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text.strip()[:120])
    await state.set_state(NewTask.desc)
    await m.answer("Vazifa tavsifini yozing (yo'q bo'lsa «-» yuboring):")


@router.message(NewTask.desc, F.text, ~F.text.in_(ADMIN_BTNS))
async def task_desc(m: Message, state: FSMContext, db: DB, cfg: Config, bot: Bot):
    data = await state.get_data()
    desc = None if m.text.strip() == "-" else m.text.strip()
    ws = week_start(today(cfg.timezone)).isoformat()
    task_id = await db.add_task(data["title"], desc, ws)
    await state.clear()
    username = (await bot.me()).username
    text = f"📌 Yangi vazifa: {data['title']}"
    if desc:
        text += f"\n\n{desc}"
    text += f"\n\nTopshirish: @{username} (shaxsiy xabarda)"
    try:
        await bot.send_message(cfg.group_id, text)
        await m.answer(f"✅ Vazifa #{task_id} qo'shildi va guruhga yuborildi.")
    except TelegramAPIError:
        await m.answer(f"✅ Vazifa #{task_id} qo'shildi, lekin guruhga yuborib bo'lmadi (bot guruhda bormi?).")


# ---------- tekshirish ----------
async def send_next(bot: Bot, db: DB, cfg: Config, chat_id: int, after_id: int = 0) -> None:
    sub = await db.next_pending(after_id)
    if not sub:
        await bot.send_message(chat_id, "✅ Tekshirilmagan ish qolmadi.")
        return
    try:
        await bot.copy_message(chat_id, cfg.storage_channel_id, sub["storage_msg_id"])
    except TelegramAPIError:
        await bot.send_message(chat_id, f"⚠️ #{sub['id']} faylini kanaldan olib bo'lmadi.")
    info = (
        f"👤 {sub['full_name']}\n📝 {sub['task_title']}\n"
        f"🗓 {sub['submit_date']} · #{sub['id']}\n\nBahoni tanlang (0–10):"
    )
    await bot.send_message(chat_id, info, reply_markup=grade_kb(sub["id"]))


@router.message(Command("tekshir"))
@router.message(F.text == A_REVIEW)
async def review(m: Message, state: FSMContext, db: DB, cfg: Config, bot: Bot):
    await state.clear()
    n = await db.pending_count()
    if n == 0:
        await m.answer("✅ Tekshirilmagan ish yo'q.")
        return
    await m.answer(f"Tekshirilmagan ishlar: {n} ta. Boshlaymiz 👇")
    await send_next(bot, db, cfg, m.chat.id)


@router.callback_query(F.data.startswith("g:"))
async def grade_cb(c: CallbackQuery, db: DB, cfg: Config, bot: Bot):
    _, sub_id_s, value = c.data.split(":")
    sub_id = int(sub_id_s)
    sub = await db.get_submission(sub_id)
    if not sub:
        await c.answer("Topilmadi", show_alert=True)
        return
    if value == "skip":
        await c.message.edit_text(c.message.text + "\n\n⏭ O'tkazib yuborildi")
        await send_next(bot, db, cfg, c.message.chat.id, after_id=sub_id)
        await c.answer()
        return
    score = int(value)
    await db.grade(sub_id, score)
    await c.message.edit_text(c.message.text.split("\n\nBahoni")[0] + f"\n\n✅ Baho: {score}/10")
    try:
        await bot.send_message(
            sub["user_id"],
            f"✅ «{sub['task_title']}» bo'yicha ishingiz baholandi: {score}/10 (#{sub_id})",
        )
    except TelegramAPIError:
        pass
    await c.answer("Saqlandi")
    await send_next(bot, db, cfg, c.message.chat.id, after_id=sub_id)


# ---------- hisobot ----------
async def build_report(db: DB, cfg: Config, offset: int) -> tuple[str, bytes]:
    start, end = week_range(today(cfg.timezone), offset)
    rows = await db.week_stats(start, end)
    last_day = date.fromisoformat(end) - timedelta(days=1)
    title = f"Haftalik natijalar ({date.fromisoformat(start):%d.%m} – {last_day:%d.%m})"

    active = sum(1 for r in rows if r["total"] > 0)
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"📊 {title}", f"Faol o'quvchilar: {active}/{len(rows)}", ""]
    for i, r in enumerate(rows):
        mark = medals[i] if i < 3 and r["total"] > 0 else f"{i + 1}."
        avg = f"{r['avg_score']:.1f}" if r["avg_score"] is not None else "—"
        lines.append(f"{mark} {r['full_name']} — {r['total']} ta ish, o'rtacha {avg}, jami {r['points']} ball")
    silent = [r["full_name"] for r in rows if r["total"] == 0]
    if silent:
        lines += ["", "❗ Hech narsa topshirmaganlar: " + ", ".join(silent)]
    return "\n".join(lines), weekly_chart(rows, title)


async def send_report(bot: Bot, chat_id: int, text: str, png: bytes, markup=None) -> None:
    await bot.send_photo(chat_id, BufferedInputFile(png, "hisobot.png"))
    await bot.send_message(chat_id, text[:4000], reply_markup=markup)


@router.message(Command("hisobot"))
@router.message(F.text.in_({A_REPORT, A_REPORT_PREV}))
async def report(m: Message, state: FSMContext, db: DB, cfg: Config, bot: Bot):
    await state.clear()
    parts = (m.text or "").split()
    offset = 1 if m.text == A_REPORT_PREV else (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0)
    students = await db.all_students()
    if not students:
        await m.answer("Hali o'quvchilar ro'yxatdan o'tmagan.")
        return
    text, png = await build_report(db, cfg, offset)
    await send_report(bot, m.chat.id, text, png, report_kb(offset))


@router.callback_query(F.data.startswith("rep:"))
async def report_to_group(c: CallbackQuery, db: DB, cfg: Config, bot: Bot):
    offset = int(c.data.split(":")[1])
    text, png = await build_report(db, cfg, offset)
    try:
        await send_report(bot, cfg.group_id, text, png)
        await c.answer("Guruhga yuborildi ✅", show_alert=True)
    except TelegramAPIError:
        await c.answer("Guruhga yuborib bo'lmadi", show_alert=True)


@router.message(Command("oquvchilar"))
@router.message(F.text == A_STUDENTS)
async def students(m: Message, state: FSMContext, db: DB):
    await state.clear()
    rows = await db.all_students()
    if not rows:
        await m.answer("Hali o'quvchilar yo'q.")
        return
    await m.answer(
        f"👥 O'quvchilar ({len(rows)}):\n\n"
        + "\n".join(f"{i}. {r['full_name']}" for i, r in enumerate(rows, 1))
    )
