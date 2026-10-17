import logging

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
from ..texts import LINE, bar, esc, hint, kv, quote, title
from ..timeutil import today, week_range, week_start

log = logging.getLogger(__name__)
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
    student = await db.get_student(uid)
    if student:
        await m.answer(
            f"{title('👋', 'Xush kelibsiz!')}\n"
            f"<b>{esc(student['full_name'])}</b>, quyidagi menyudan tanlang 👇",
            reply_markup=main_kb(),
        )
        return
    if not await in_group(bot, cfg.group_id, uid):
        await m.answer(
            f"{title('🔒', 'Kirish yopiq')}\n"
            "Bu bot faqat guruh o'quvchilari uchun.\n"
            "Avval o'quv guruhiga qo'shiling, keyin /start ni qayta bosing."
        )
        return
    await m.answer(
        f"{title('👋', 'Assalomu alaykum!')}\n"
        "Ro'yxatdan o'tish uchun <b>ism-familiyangizni</b> yozing:"
    )
    await state.set_state(Reg.name)


@router.message(Reg.name, F.text)
async def reg_name(m: Message, state: FSMContext, db: DB):
    name = m.text.strip()[:80]
    if len(name) < 3:
        await m.answer("⚠️ Iltimos, <b>to'liq ism-familiyangizni</b> yozing.")
        return
    await db.add_student(m.from_user.id, name, m.from_user.username)
    await state.clear()
    await m.answer(
        f"{title('✅', 'Roʻyxatdan oʻtdingiz')}\n"
        f"👤 <b>{esc(name)}</b>\n\nMenyudan foydalaning 👇",
        reply_markup=main_kb(),
    )


async def _ensure_student(m: Message, db: DB) -> bool:
    if await db.get_student(m.from_user.id):
        return True
    await m.answer("⚠️ Avval /start orqali ro'yxatdan o'ting.")
    return False


@router.message(F.text == BTN_TASKS)
async def show_tasks(m: Message, state: FSMContext, db: DB, cfg: Config):
    await state.clear()
    if not await _ensure_student(m, db):
        return
    ws = week_start(today(cfg.timezone)).isoformat()
    tasks = await db.tasks_for_week(ws)
    if not tasks:
        await m.answer("📭 Bu hafta uchun hali vazifa berilmagan.")
        return
    blocks = []
    for i, t in enumerate(tasks, 1):
        block = f"<b>{i}. {esc(t['title'])}</b>"
        if t["description"]:
            block += "\n" + quote(t["description"])
        blocks.append(block)
    await m.answer(title("📋", "Shu haftaning vazifalari") + "\n" + "\n\n".join(blocks))


@router.message(F.text == BTN_SUBMIT)
async def choose_task(m: Message, state: FSMContext, db: DB, cfg: Config):
    await state.clear()
    if not await _ensure_student(m, db):
        return
    ws = week_start(today(cfg.timezone)).isoformat()
    tasks = await db.tasks_for_week(ws)
    if not tasks:
        await m.answer("📭 Bu hafta uchun hali vazifa berilmagan.")
        return
    await m.answer(
        f"{title('📤', 'Vazifa topshirish')}\nQaysi vazifani topshirasiz? 👇",
        reply_markup=tasks_kb(tasks),
    )


@router.callback_query(F.data.startswith("task:"))
async def task_chosen(c: CallbackQuery, state: FSMContext, db: DB):
    task = await db.get_task(int(c.data.split(":")[1]))
    if not task:
        await c.answer("Vazifa topilmadi", show_alert=True)
        return
    await state.set_state(Submit.sending)
    await state.update_data(task_id=task["id"])
    await c.message.answer(
        f"{title('📌', task['title'])}\n"
        "Ishingizni yuboring:\n"
        "🎥 video  ·  📄 PDF  ·  🖼 rasm  ·  🎤 ovoz  ·  ✏️ matn\n\n"
        f"Bir nechta fayl yuborishingiz mumkin.\nTugatgach <b>{esc(BTN_DONE)}</b> tugmasini bosing 👇",
        reply_markup=done_kb(),
    )
    await c.answer()


@router.message(Submit.sending, F.text == BTN_DONE)
async def submit_done(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        f"{title('🎉', 'Rahmat!')}\nIshlaringiz o'qituvchiga yuborildi.",
        reply_markup=main_kb(),
    )


@router.message(Submit.sending, ~F.text.in_(MENU_TEXTS))
async def receive_work(m: Message, state: FSMContext, db: DB, cfg: Config, bot: Bot):
    data = extract(m)
    if data is None:
        await m.answer("⚠️ Bu turdagi xabar qabul qilinmaydi.\nVideo, PDF, rasm, ovoz yoki matn yuboring.")
        return
    kind, file_id, text = data
    task_id = (await state.get_data())["task_id"]
    student = await db.get_student(m.from_user.id)
    try:
        copied = await bot.copy_message(cfg.storage_channel_id, m.chat.id, m.message_id)
    except TelegramAPIError as e:
        log.error("Kanalga nusxalab bo'lmadi (STORAGE_CHANNEL_ID=%s): %s", cfg.storage_channel_id, e)
        for admin_id in cfg.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    f"{title('⚠️', 'Ishni kanalga saqlab bo‘lmadi')}\n"
                    f"{kv('❓', 'Sabab', e, code=True)}\n\n"
                    "Tekshiring: <code>STORAGE_CHANNEL_ID</code> to'g'rimi (<code>-100</code> bilan boshlanadi) "
                    "va bot kanalda administratormi?",
                )
            except TelegramAPIError:
                pass
        await m.answer("❌ <b>Saqlashda xatolik.</b>\nO'qituvchiga xabar yuborildi, birozdan keyin qayta urinib ko'ring.")
        return
    day = today(cfg.timezone)
    sub_id = await db.add_submission(
        m.from_user.id, task_id, kind, text, file_id, copied.message_id, day.isoformat()
    )
    task = await db.get_task(task_id)
    try:
        await bot.send_message(
            cfg.storage_channel_id,
            f"📥 <b>Ish #{sub_id}</b>\n{LINE}\n"
            f"{kv('👤', 'Oʻquvchi', student['full_name'])}\n"
            f"{kv('📝', 'Vazifa', task['title'])}\n"
            f"{kv('🗓', 'Sana', day.isoformat(), code=True)}",
            reply_to_message_id=copied.message_id,
        )
    except TelegramAPIError:
        pass
    await m.answer(f"✅ <b>Qabul qilindi</b> · <code>#{sub_id}</code>")


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

    avg = summary["avg_score"]
    avg_txt = f"{avg:.1f}" if avg is not None else "—"
    lines = [
        title("📊", "Sizning natijangiz"),
        kv("📤", "Topshirilgan ishlar", summary["total"], code=True),
        kv("✅", "Baholanganlari", summary["graded"], code=True),
        kv("⭐️", "O'rtacha ball", avg_txt, code=True),
        bar(avg),
    ]
    if week_row:
        lines += [
            "",
            title("🗓", "Shu hafta"),
            kv("📤", "Ishlar", week_row["total"], code=True),
            kv("🏅", "Jami ball", week_row["points"], code=True),
        ]
        if rank:
            lines.append(kv("🏆", "Guruhdagi o'rningiz", f"{rank}/{len(rows)}", code=True))
    await m.answer("\n".join(lines))

    series = await db.student_weekly_series(uid, d, 8)
    if any(v > 0 for _, v in series):
        png = progress_chart(series, "Haftalar bo'yicha o'rtacha ball")
        await m.answer_photo(BufferedInputFile(png, "natija.png"))
    else:
        await m.answer(hint("Baholangan ishlar paydo bo'lgach, o'sish grafigi shu yerda chiqadi."))
