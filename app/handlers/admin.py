from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, TelegramObject

from ..backup import parse_backup, send_backup
from ..charts import weekly_chart
from ..config import Config
from ..db import DB
from ..export import PERIODS, build_stats_xlsx
from ..keyboards import (
    A_CANCEL,
    A_EXCEL,
    A_REPORT,
    A_REPORT_PREV,
    A_REVIEW,
    A_STUDENTS,
    A_TASK,
    admin_kb,
    board_kb,
    excel_kb,
    grade_kb,
    report_kb,
    restore_kb,
)
from ..texts import bar, esc, hint, kv, quote, score_badge, split_lines, title
from ..timeutil import today, week_range, week_start


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, cfg: Config) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in cfg.admin_ids)


router = Router()
router.message.filter(F.chat.type == "private", IsAdmin())
router.callback_query.filter(IsAdmin())


ADMIN_BTNS = {A_TASK, A_REVIEW, A_REPORT, A_REPORT_PREV, A_STUDENTS, A_EXCEL, A_CANCEL}


class NewTask(StatesGroup):
    title = State()
    desc = State()


HELP = (
    f"{title('👨‍🏫', 'Admin paneli')}\n"
    "Pastdagi tugmalardan foydalaning 👇\n\n"
    f"<b>{esc(A_TASK)}</b> — yangi vazifa (guruhga e'lon qilinadi)\n"
    f"<b>{esc(A_REVIEW)}</b> — ishlarni ko'rib baholash\n"
    f"<b>{esc(A_REPORT)}</b> — shu haftalik statistika\n"
    f"<b>{esc(A_REPORT_PREV)}</b> — o'tgan hafta hisoboti\n"
    f"<b>{esc(A_STUDENTS)}</b> — guruh o'quvchilari: 🟢 topshirgan / 🔴 topshirmagan\n"
    f"<b>{esc(A_EXCEL)}</b> — statistikani Excel fayl qilib olish\n"
    "<b>/zaxira</b> — bazaning zaxira nusxasi (tiklash: shu faylni botga yuboring)"
)


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(HELP, reply_markup=admin_kb())


@router.message(Command("bekor"))
@router.message(F.text == A_CANCEL)
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("❌ <b>Bekor qilindi.</b>", reply_markup=admin_kb())


# ---------- vazifa qo'shish ----------
@router.message(Command("vazifa"))
@router.message(F.text == A_TASK)
async def new_task(m: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewTask.title)
    await m.answer(f"{title('➕', 'Yangi vazifa')}\n1/2 · Vazifa <b>nomini</b> yozing:")


@router.message(NewTask.title, F.text, ~F.text.in_(ADMIN_BTNS))
async def task_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text.strip()[:120])
    await state.set_state(NewTask.desc)
    await m.answer("2/2 · Vazifa <b>tavsifini</b> yozing\n(yo'q bo'lsa <code>-</code> yuboring):")


@router.message(NewTask.desc, F.text, ~F.text.in_(ADMIN_BTNS))
async def task_desc(m: Message, state: FSMContext, db: DB, cfg: Config, bot: Bot):
    data = await state.get_data()
    desc = None if m.text.strip() == "-" else m.text.strip()
    ws = week_start(today(cfg.timezone)).isoformat()
    task_id = await db.add_task(data["title"], desc, ws)
    await state.clear()
    username = (await bot.me()).username
    text = title("📌", f"Yangi vazifa: {data['title']}")
    if desc:
        text += "\n" + quote(desc)
    text += f"\n\n📤 Topshirish: @{esc(username)} <i>(shaxsiy xabarda)</i>"
    try:
        await bot.send_message(cfg.group_id, text)
        await m.answer(f"✅ <b>Vazifa qo'shildi</b> · <code>#{task_id}</code>\nGuruhga yuborildi.")
    except TelegramAPIError:
        await m.answer(
            f"✅ <b>Vazifa qo'shildi</b> · <code>#{task_id}</code>\n"
            "⚠️ Lekin guruhga yuborib bo'lmadi (bot guruhda bormi?)."
        )


# ---------- tekshirish ----------
def review_card(sub: dict, footer: str) -> str:
    heading = title("📝", "Ish #" + str(sub["id"]))
    return (
        f"{heading}\n"
        f"{kv('👤', 'Oʻquvchi', sub['full_name'])}\n"
        f"{kv('📌', 'Vazifa', sub['task_title'])}\n"
        f"{kv('🗓', 'Sana', sub['submit_date'], code=True)}\n\n"
        f"{footer}"
    )


async def send_next(bot: Bot, db: DB, cfg: Config, chat_id: int, after_id: int = 0) -> None:
    sub = await db.next_pending(after_id)
    if not sub:
        await bot.send_message(chat_id, "🎉 <b>Tekshirilmagan ish qolmadi.</b>")
        return
    try:
        await bot.copy_message(chat_id, cfg.storage_channel_id, sub["storage_msg_id"])
    except TelegramAPIError:
        await bot.send_message(chat_id, f"⚠️ <code>#{sub['id']}</code> faylini kanaldan olib bo'lmadi.")
    await bot.send_message(
        chat_id,
        review_card(sub, "⭐️ <b>Bahoni tanlang</b> <code>(0–10)</code>:"),
        reply_markup=grade_kb(sub["id"]),
    )


@router.message(Command("tekshir"))
@router.message(F.text == A_REVIEW)
async def review(m: Message, state: FSMContext, db: DB, cfg: Config, bot: Bot):
    await state.clear()
    n = await db.pending_count()
    if n == 0:
        await m.answer("🎉 <b>Tekshirilmagan ish yo'q.</b>")
        return
    await m.answer(f"📬 Tekshirilmagan ishlar: <code>{n}</code> ta\nBoshlaymiz 👇")
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
        await c.message.edit_text(review_card(sub, "⏭ <i>O'tkazib yuborildi</i>"))
        await send_next(bot, db, cfg, c.message.chat.id, after_id=sub_id)
        await c.answer()
        return
    score = int(value)
    await db.grade(sub_id, score)
    await c.message.edit_text(review_card(sub, f"✅ <b>Baho:</b> {score_badge(score)}\n{bar(score)}"))
    try:
        await bot.send_message(
            sub["user_id"],
            f"{title('✅', 'Ishingiz baholandi')}\n"
            f"{kv('📌', 'Vazifa', sub['task_title'])}\n"
            f"⭐️ <b>Ball:</b> {score_badge(score)}\n{bar(score)}\n"
            f"<i>Ish raqami: #{sub_id}</i>",
        )
    except TelegramAPIError:
        pass
    await c.answer("Saqlandi")
    await send_next(bot, db, cfg, c.message.chat.id, after_id=sub_id)


# ---------- hisobot ----------
async def build_report(db: DB, cfg: Config, offset: int) -> tuple[list[str], bytes]:
    start, end = week_range(today(cfg.timezone), offset)
    rows = await db.week_stats(start, end)
    last_day = date.fromisoformat(end) - timedelta(days=1)
    period = f"{date.fromisoformat(start):%d.%m} – {last_day:%d.%m}"

    active = sum(1 for r in rows if r["total"] > 0)
    medals = ["🥇", "🥈", "🥉"]
    lines = [
        title("📊", f"Haftalik natijalar · {period}"),
        kv("👥", "Faol o'quvchilar", f"{active}/{len(rows)}", code=True),
        "",
    ]
    for i, r in enumerate(rows):
        mark = medals[i] if i < 3 and r["total"] > 0 else f"<code>{i + 1:>2}.</code>"
        avg = r["avg_score"]
        avg_txt = f"{avg:.1f}" if avg is not None else "—"
        lines.append(f"{mark} <b>{esc(r['full_name'])}</b>")
        lines.append(
            f"      📤 <code>{r['total']}</code>  ⭐️ <code>{avg_txt}</code>  🏅 <code>{r['points']}</code>  {bar(avg, 5)}"
        )
    silent = [r["full_name"] for r in rows if r["total"] == 0]
    if silent:
        lines += ["", "❗ <b>Hech narsa topshirmaganlar:</b>"]
        lines += [f"• {esc(n)}" for n in silent]
    lines += ["", "<i>📤 ishlar · ⭐️ o'rtacha ball · 🏅 jami ball</i>"]
    return split_lines(lines), weekly_chart(rows, f"Haftalik natijalar ({period})")


async def send_report(bot: Bot, chat_id: int, parts: list[str], png: bytes, markup=None) -> None:
    await bot.send_photo(chat_id, BufferedInputFile(png, "hisobot.png"))
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        await bot.send_message(chat_id, part, reply_markup=markup if last else None)


@router.message(Command("hisobot"))
@router.message(F.text.in_({A_REPORT, A_REPORT_PREV}))
async def report(m: Message, state: FSMContext, db: DB, cfg: Config, bot: Bot):
    await state.clear()
    parts = (m.text or "").split()
    offset = 1 if m.text == A_REPORT_PREV else (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0)
    students = await db.all_students()
    if not students:
        await m.answer("📭 Hali o'quvchilar ro'yxatdan o'tmagan.")
        return
    texts, png = await build_report(db, cfg, offset)
    await send_report(bot, m.chat.id, texts, png, report_kb(offset))


@router.callback_query(F.data.startswith("rep:"))
async def report_to_group(c: CallbackQuery, db: DB, cfg: Config, bot: Bot):
    offset = int(c.data.split(":")[1])
    texts, png = await build_report(db, cfg, offset)
    try:
        await send_report(bot, cfg.group_id, texts, png)
        await c.answer("Guruhga yuborildi ✅", show_alert=True)
    except TelegramAPIError:
        await c.answer("Guruhga yuborib bo'lmadi", show_alert=True)


# ---------- o'quvchilar: 🟢 topshirgan / 🔴 topshirmagan + filtr ----------
def _fmt_score(v: float | None) -> str:
    return "⏳" if v is None else f"{round(v, 1):g}/10"


def _fit(lines: list[str]) -> str:
    parts = split_lines(lines)
    text = parts[0]
    if len(parts) > 1:
        text += "\n<i>… ro'yxat uzun, filtrdan foydalaning</i>"
    return text


async def build_board(db: DB, cfg: Config, task_id: int, status: str):
    ws = week_start(today(cfg.timezone)).isoformat()
    tasks = await db.tasks_for_week(ws)
    roster = await db.all_students()
    if not roster:
        return (
            "📭 Hali o'quvchilar yo'q.\n"
            + hint("Guruh a'zolari guruhda yozgach yoki botga /start bosgach shu yerda paydo bo'ladi."),
            None,
        )
    if not tasks:
        lines = [title("👥", f"O'quvchilar · {len(roster)} ta")]
        lines += [
            f"<code>{i:>2}.</code> {esc(r['full_name'])}{'' if r['started'] else ' ⚠️'}"
            for i, r in enumerate(roster, 1)
        ]
        lines += ["", "📭 Bu hafta uchun hali vazifa berilmagan.", hint("⚠️ — botga /start bosmagan")]
        return _fit(lines), None

    ids = [t["id"] for t in tasks]
    if task_id not in ids:
        task_id = 0
    if status not in ("a", "g", "r"):
        status = "a"
    subs = await db.week_submissions(ws)

    entries = []
    for s in roster:
        done = subs.get(s["user_id"], {})
        ok = (task_id in done) if task_id else all(i in done for i in ids)
        entries.append((s, ok, done))
    n_ok = sum(1 for _, ok, _ in entries if ok)
    n_bad = len(entries) - n_ok
    shown = [e for e in entries if status == "a" or (status == "g" and e[1]) or (status == "r" and not e[1])]

    scope = next(t["title"] for t in tasks if t["id"] == task_id) if task_id else "Hamma vazifalar"
    lines = [
        title("👥", f"O'quvchilar · {len(roster)} ta"),
        kv("📌", "Vazifa", scope),
        f"{kv('🟢', 'Topshirgan', n_ok, code=True)}   {kv('🔴', 'Topshirmagan', n_bad, code=True)}",
    ]
    if not task_id and len(tasks) > 1:
        lines.append("")
        lines += [f"<code>{i}</code> {esc(t['title'])}" for i, t in enumerate(tasks, 1)]
    lines.append("")
    if not shown:
        lines.append(hint("Bu filtrda hech kim yo'q."))
    for s, ok, done in shown:
        extra = ""
        if task_id and ok:
            extra = f" · <code>{_fmt_score(done[task_id])}</code>"
        elif not task_id and len(ids) > 1:
            extra = "  " + "".join("🟢" if i in done else "🔴" for i in ids)
        warn = "" if s["started"] else " ⚠️"
        lines.append(f"{'🟢' if ok else '🔴'} <b>{esc(s['full_name'])}</b>{extra}{warn}")
    lines += ["", hint("⚠️ — botga /start bosmagan (eslatma ola olmaydi)")]
    return _fit(lines), board_kb(tasks, task_id, status)


@router.message(Command("oquvchilar"))
@router.message(F.text == A_STUDENTS)
async def students(m: Message, state: FSMContext, db: DB, cfg: Config):
    await state.clear()
    text, kb = await build_board(db, cfg, 0, "a")
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("sb:"))
async def board_cb(c: CallbackQuery, db: DB, cfg: Config):
    _, task_s, status = c.data.split(":")
    text, kb = await build_board(db, cfg, int(task_s), status)
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:  # "message is not modified"
        pass
    await c.answer()


# ---------- Excel hisobot ----------
@router.message(Command("excel"))
@router.message(F.text == A_EXCEL)
async def excel_menu(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        f"{title('📥', 'Excel hisobot')}\nQaysi davr uchun statistika kerak? 👇",
        reply_markup=excel_kb(),
    )


@router.callback_query(F.data.startswith("xl:"))
async def excel_cb(c: CallbackQuery, db: DB, cfg: Config, bot: Bot):
    period = c.data.split(":")[1]
    if period not in PERIODS:
        await c.answer()
        return
    await c.answer("⏳ Tayyorlanmoqda…")
    data, name = await build_stats_xlsx(db, cfg, period)
    await bot.send_document(
        c.message.chat.id,
        BufferedInputFile(data, name),
        caption=f"{title('📥', 'Statistika')} · {esc(PERIODS[period])}\n"
        + hint("Varaqlar: Reyting · Vazifalar holati (🟢/🔴) · Barcha ishlar"),
    )


# ---------- zaxira va tiklash ----------
_pending_restore: dict[int, dict] = {}


@router.message(Command("zaxira"))
async def backup_cmd(m: Message, db: DB, cfg: Config, bot: Bot):
    await m.answer("⏳ Zaxira tayyorlanmoqda…")
    await send_backup(bot, m.chat.id, db, cfg)


@router.message(F.document)
async def restore_file(m: Message, bot: Bot):
    name = (m.document.file_name or "").lower()
    if not (name.endswith(".json.gz") or name.endswith(".json")):
        await m.answer(
            "📎 Zaxirani tiklash uchun botdan olingan <code>zaxira_….json.gz</code> faylini yuboring."
        )
        return
    if (m.document.file_size or 0) > 15 * 1024 * 1024:
        await m.answer("⚠️ Fayl juda katta.")
        return
    try:
        buf = await bot.download(m.document)
        tables = parse_backup(buf.read())
    except ValueError as e:
        await m.answer(f"⚠️ {esc(str(e))}")
        return
    except TelegramAPIError as e:
        await m.answer(f"⚠️ Faylni yuklab bo'lmadi: {esc(str(e))[:200]}")
        return
    _pending_restore[m.from_user.id] = tables
    await m.answer(
        f"{title('♻️', 'Zaxiradan tiklash')}\n"
        f"{kv('👥', 'O‘quvchilar', len(tables['students']), code=True)}   "
        f"{kv('📋', 'Vazifalar', len(tables['tasks']), code=True)}   "
        f"{kv('📤', 'Ishlar', len(tables['submissions']), code=True)}\n\n"
        "⚠️ Hozirgi barcha ma'lumotlar <b>shu fayl bilan almashtiriladi</b>. "
        "Almashtirishdan oldin hozirgi bazaning zaxirasi ham yuboriladi.",
        reply_markup=restore_kb(),
    )


@router.callback_query(F.data.startswith("rs:"))
async def restore_cb(c: CallbackQuery, db: DB, cfg: Config, bot: Bot):
    tables = _pending_restore.pop(c.from_user.id, None)
    if c.data == "rs:no" or tables is None:
        await c.message.edit_text("❌ Tiklash bekor qilindi." if c.data == "rs:no" else "⌛ So'rov eskirgan, faylni qayta yuboring.")
        await c.answer()
        return
    await c.answer("⏳")
    try:
        await send_backup(bot, c.message.chat.id, db, cfg)  # xavfsizlik uchun hozirgi holat
        counts = await db.import_all(tables)
    except Exception as e:  # tranzaksiya qaytarilgan — eski ma'lumot joyida
        await c.message.edit_text(f"⚠️ Tiklanmadi, eski ma'lumotlar joyida: {esc(str(e))[:300]}")
        return
    await c.message.edit_text(
        f"{title('✅', 'Tiklandi')}\n"
        f"{kv('👥', 'O‘quvchilar', counts['students'], code=True)}   "
        f"{kv('📋', 'Vazifalar', counts['tasks'], code=True)}   "
        f"{kv('📤', 'Ishlar', counts['submissions'], code=True)}"
    )
