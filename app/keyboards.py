from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_SUBMIT = "📤 Vazifa topshirish"
BTN_TASKS = "📋 Vazifalar"
BTN_STATS = "📊 Mening natijam"
BTN_DONE = "✅ Tayyor"

MENU_TEXTS = {BTN_SUBMIT, BTN_TASKS, BTN_STATS}


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SUBMIT)], [KeyboardButton(text=BTN_TASKS), KeyboardButton(text=BTN_STATS)]],
        resize_keyboard=True,
    )


A_TASK = "➕ Yangi vazifa"
A_REVIEW = "📝 Tekshirish"
A_REPORT = "📊 Hisobot"
A_REPORT_PREV = "📊 O'tgan hafta"
A_STUDENTS = "👥 O'quvchilar"
A_CANCEL = "❌ Bekor qilish"


def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=A_TASK), KeyboardButton(text=A_REVIEW)],
            [KeyboardButton(text=A_REPORT), KeyboardButton(text=A_REPORT_PREV)],
            [KeyboardButton(text=A_STUDENTS), KeyboardButton(text=A_CANCEL)],
        ],
        resize_keyboard=True,
    )


def done_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_DONE)]], resize_keyboard=True)


def tasks_kb(tasks: list[dict], done: frozenset[int] | set[int] = frozenset()) -> InlineKeyboardMarkup:
    """🟢 — topshirilgan, 🔴 — topshirilmagan."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'🟢' if t['id'] in done else '🔴'} {t['title'][:55]}",
                    callback_data=f"task:{t['id']}",
                )
            ]
            for t in tasks
        ]
    )


def board_kb(tasks: list[dict], task_id: int, status: str) -> InlineKeyboardMarkup:
    """Admin uchun filtr: vazifa bo'yicha va holat bo'yicha (a=hamma, g=topshirgan, r=topshirmagan)."""

    def mark(text: str, on: bool) -> str:
        return f"• {text}" if on else text

    task_btns = [InlineKeyboardButton(text=mark("📚 Hamma vazifa", task_id == 0), callback_data=f"sb:0:{status}")]
    task_btns += [
        InlineKeyboardButton(text=mark(str(i), task_id == t["id"]), callback_data=f"sb:{t['id']}:{status}")
        for i, t in enumerate(tasks, 1)
    ]
    rows = [task_btns[:4]] + [task_btns[i : i + 5] for i in range(4, len(task_btns), 5)]
    rows.append([InlineKeyboardButton(text=mark("👥 Hamma o'quvchi", status == "a"), callback_data=f"sb:{task_id}:a")])
    rows.append(
        [
            InlineKeyboardButton(text=mark("🟢 Topshirgan", status == "g"), callback_data=f"sb:{task_id}:g"),
            InlineKeyboardButton(text=mark("🔴 Topshirmagan", status == "r"), callback_data=f"sb:{task_id}:r"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def grade_kb(sub_id: int) -> InlineKeyboardMarkup:
    def row(nums):
        return [InlineKeyboardButton(text=str(n), callback_data=f"g:{sub_id}:{n}") for n in nums]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            row(range(0, 6)),
            row(range(6, 11)),
            [InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=f"g:{sub_id}:skip")],
        ]
    )


def report_kb(offset: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📣 Guruhga yuborish", callback_data=f"rep:{offset}")]
        ]
    )
