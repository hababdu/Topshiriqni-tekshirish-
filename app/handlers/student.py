from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..charts import progress_chart
from ..config import Config
from ..db import DB
from ..keyboards import (
    BTN_DONE,
    BTN_STATS,
    BTN_SUBMIT,
    BTN_TASKS,
    MENU_TEXTS,
    done_kb,
    main_kb,
    tasks_kb,
)
from ..timeutil import today, week_range, week_start

router = Router()
router.message.filter(F.chat.type == "private")


class Reg(StatesGroup):
    name = State()


class Submit(StatesGroup):
    sending = State()


async def in_group(bot: Bot, group_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(group_id, user_id)
    except TelegramAPIError:
        return False
    if member.status in ("member", "administrator", "creator"):
        return True
    return member.status == "restricted" and getattr(member, "is_member", False)


def extract(m: Message) -> tuple[str, str | None, str | None] | None:
    """(tur, file_id, matn/izoh) yoki None."""
    if m.photo:
        return "photo", m.photo[-1].file_id, m.caption
    if m.video:
        return "video", m.video.file_id, m.caption
    if m.document:
        return "document", m.document.file_id, m.caption
    if m.voice:
        return "voice", m.voice.file_id, m.caption
    if m.video_note:
        return "video_note", m.video_note.file_id, None
    if m.audio:
        return "audio", m.audio.file_id, m.caption
    if m.text:
        return "text", None, m.text
    return None


@router.message(CommandStart())
async def start(m: Message, state: FSMContext, db: DB, cfg: Config, bot: Bot):
    await state.clear()
    uid = m.from_user.id
    if await db.get_student(uid):
        await m.answer("Xush kelibsiz! Menyudan tanlang 👇", reply_markup=main_kb())
        return
    if not await in_group(bot, cfg.group_id, uid):
        await m.answer(
            "Bu bot faqat guruh o'quvchilari uchun. Avval o'quv guruhiga qo'shiling, "
            "keyin /start ni qayta bosing."
        )
        return
    await m.answer("Assalomu alaykum! Ism-familiyangizni yozing:")
    await state.set_state(Reg.name)


@router.message(Reg.name, F.text)
async def reg_name(m: Message, state: FSMContext, db: DB):
    name = m.text.strip()[:80]
    if len(name) < 3:
        await m.answer("Iltimos, to'liq ism-familiyangizni yozing.")
        return
    await db.add_student(m.from_user.id, name, m.from_user.username)
    await state.clear()
    await m.answer(f"✅ Ro'yxatdan o'tdingiz, {name}!", reply_markup=main_kb())


async def _ensure_student(m: Message, db: DB) -> bool:
    if await db.get_student(m.from_user.id):
        return True
    await m.answer("Avval /start orqali ro'yxatdan o'ting.")
    return False


@router.message(F.text == BTN_TASKS)
async def show_tasks(m: Message, state: FSMContext, db: DB, cfg: Config):
    await state.clear()
    if not await _ensure_student(m, db):
        return
    ws = week_start(today(cfg.timezone)).isoformat()
    tasks = await db.tasks_for_week(ws)
    if not tasks:
        await m.answer("Bu hafta uchun hali vazifa berilmagan.")
        return
    text = "📋 Shu haftaning vazifalari:\n\n" + "\n\n".join(
        f"▫️ {t['title']}\n{t['description'] or ''}".strip() for t in tasks
    )
    await m.answer(text)


@router.message(F.text == BTN_SUBMIT)
async def choose_task(m: Message, state: FSMContext, db: DB, cfg: Config):
    await state.clear()
    if not await _ensure_student(m, db):
        return
    ws = week_start(today(cfg.timezone)).isoformat()
    tasks = await db.tasks_for_week(ws)
    if not tasks:
        await m.answer("Bu hafta uchun hali vazifa berilmagan.")
        return
    await m.answer("Qaysi vazifani topshirasiz?", reply_markup=tasks_kb(tasks))


@router.callback_query(F.data.startswith("task:"))
async def task_chosen(c: CallbackQuery, state: FSMContext, db: DB):
    task = await db.get_task(int(c.data.split(":")[1]))
    if not task:
        await c.answer("Vazifa topilmadi", show_alert=True)
        return
    await state.set_state(Submit.sending)
    await state.update_data(task_id=task["id"])
    await c.message.answer(
        f"📌 {task['title']}\n\nVideo, PDF, rasm yoki matn yuboring (bir nechta bo'lishi mumkin). "
        f"Tugatgach «{BTN_DONE}» ni bosing.",
        reply_markup=done_kb(),
    )
    await c.answer()


@router.message(Submit.sending, F.text == BTN_DONE)
async def submit_done(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Rahmat! Ishlaringiz o'qituvchiga yuborildi 👍", reply_markup=main_kb())


@router.message(Submit.sending, ~F.text.in_(MENU_TEXTS))
async def receive_work(m: Message, state: FSMContext, db: DB, cfg: Config, bot: Bot):
    data = extract(m)
    if data is None:
        await m.answer("Bu turdagi xabar qabul qilinmaydi. Video, PDF, rasm, ovoz yoki matn yuboring.")
        return
    kind, file_id, text = data
    task_id = (await state.get_data())["task_id"]
    student = await db.get_student(m.from_user.id)
    try:
        copied = await bot.copy_message(cfg.storage_channel_id, m.chat.id, m.message_id)
    except TelegramAPIError:
        await m.answer("❌ Saqlashda xatolik. Birozdan keyin qayta urinib ko'ring.")
        return
    day = today(cfg.timezone)
    sub_id = await db.add_submission(
        m.from_user.id, task_id, kind, text, file_id, copied.message_id, day.isoformat()
    )
    task = await db.get_task(task_id)
    try:
        await bot.send_message(
            cfg.storage_channel_id,
            f"📥 #{sub_id} · {student['full_name']}\n📝 {task['title']}\n🗓 {day.isoformat()}",
            reply_to_message_id=copied.message_id,
        )
    except TelegramAPIError:
        pass
    await m.answer(f"✅ Qabul qilindi (#{sub_id}).")


@router.message(F.text == BTN_STATS)
async def my_stats(m: Message, state: FSMContext, db: DB, cfg: Config):
    await state.clear()
    if not await _ensure_student(m, db):
        return
    uid = m.from_user.id
    d = today(cfg.timezone)
    summary = await db.student_summary(uid)
    start, end = week_range(d, 0)
    rows = await db.week_stats(start, end)
    rank = next((i + 1 for i, r in enumerate(rows) if r["user_id"] == uid), None)
    week_row = next((r for r in rows if r["user_id"] == uid), None)

    avg_all = f"{summary['avg_score']:.1f}" if summary["avg_score"] is not None else "—"
    lines = [
        "📊 Sizning natijangiz",
        "",
        f"Jami topshirilgan ishlar: {summary['total']}",
        f"Baholanganlari: {summary['graded']}",
        f"O'rtacha ball: {avg_all}",
    ]
    if week_row:
        lines += ["", f"Shu hafta: {week_row['total']} ta ish, {week_row['points']} ball"]
        if rank:
            lines.append(f"Guruhdagi o'rningiz: {rank}/{len(rows)}")
    await m.answer("\n".join(lines))

    series = await db.student_weekly_series(uid, d, 8)
    if any(v > 0 for _, v in series):
        png = progress_chart(series, "Haftalar bo'yicha o'rtacha ball")
        await m.answer_photo(BufferedInputFile(png, "natija.png"))
