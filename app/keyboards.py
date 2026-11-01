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
A_EXCEL = "📥 Excel"
A_CANCEL = "❌ Bekor qilish"


def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=A_TASK), KeyboardButton(text=A_REVIEW)],
            [KeyboardButton(text=A_REPORT), KeyboardButton(text=A_REPORT_PREV)],
            [KeyboardButton(text=A_STUDENTS), KeyboardButton(text=A_EXCEL)],
            [KeyboardButton(text=A_CANCEL)],
        ],
        resize_keyboard=True,
    )


def done_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_DONE)]], resize_keyboard=True)


def tasks_kb(
    tasks: list[dict], done: frozenset[int] | set[int] = frozenset(), returned: frozenset[int] | set[int] = frozenset()
) -> InlineKeyboardMarkup:
    """🟢 — topshirilgan, 🔁 — qaytarilgan (qayta topshirish kerak), 🔴 — topshirilmagan."""

    def mark(tid: int) -> str:
        return "🟢" if tid in done else "🔁" if tid in returned else "🔴"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{mark(t['id'])} {t['title'][:55]}", callback_data=f"task:{t['id']}")]
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


def grade_kb(first_id: int, last_id: int, scope: int = 0, mode: str = "p") -> InlineKeyboardMarkup:
    """Baho tugmalari. first_id..last_id — shu o'quvchining shu vazifadagi ko'rsatilgan fayllari,
    scope — qaysi vazifa tekshirilayotgani (0 = hammasi), mode — p (tekshirilmaganlar) / g (qayta ko'rish)."""
    key = f"{first_id}:{last_id}:{scope}:{mode}"

    def row(nums):
        return [InlineKeyboardButton(text=str(n), callback_data=f"g:{key}:{n}") for n in nums]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            row(range(0, 6)),
            row(range(6, 11)),
            [
                InlineKeyboardButton(text="↩️ Qaytarish", callback_data=f"g:{key}:ret"),
                InlineKeyboardButton(text="⏭ O'tkazish", callback_data=f"g:{key}:skip"),
            ],
        ]
    )


REVIEW_FILTERS = {
    "p": "⏳ Tekshirilmagan",
    "d": "🟢 Tekshirilgan",
    "r": "🔁 Qaytarilgan",
    "a": "📚 Hammasi",
}


def task_label(t: dict) -> str:
    """Vazifa tugmasidagi belgi va sonlar: ⏳ kutmoqda, 🔁 qaytarilgan, 🟢 hammasi tekshirilgan, ⚪ ish yo'q."""
    if t["p"]:
        mark = "⏳"
    elif t["r"]:
        mark = "🔁"
    elif t["g"]:
        mark = "🟢"
    else:
        mark = "⚪"
    parts = [f"{e}{n}" for e, n in (("⏳", t["p"]), ("🟢", t["g"]), ("🔁", t["r"])) if n]
    return f"{mark} {t['title'][:34]}" + (" · " + " ".join(parts) if parts else "")


def review_menu_kb(tasks: list[dict], flt: str) -> InlineKeyboardMarkup:
    """Tekshirish menyusi: tepada filtrlar, pastda vazifalar (belgi bilan)."""
    def f(key: str):
        text = REVIEW_FILTERS[key]
        return InlineKeyboardButton(text=f"• {text}" if key == flt else text, callback_data=f"rf:{key}")

    rows = [[f("p"), f("d")], [f("r"), f("a")]]
    rows += [[InlineKeyboardButton(text=task_label(t), callback_data=f"rt:{t['id']}:{flt}")] for t in tasks]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def task_panel_kb(task_id: int, flt: str, n_pending: int, n_graded: int) -> InlineKeyboardMarkup:
    rows = []
    if n_pending:
        rows.append([InlineKeyboardButton(text=f"▶️ Tekshirishni boshlash · ⏳ {n_pending}", callback_data=f"rv:{task_id}:p")])
    if n_graded:
        rows.append([InlineKeyboardButton(text=f"✏️ Baholanganlarni qayta ko'rish · 🟢 {n_graded}", callback_data=f"rv:{task_id}:g")])
    rows.append([InlineKeyboardButton(text="◀️ Vazifalar ro'yxati", callback_data=f"rf:{flt}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def report_kb(offset: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📣 Guruhga yuborish", callback_data=f"rep:{offset}")]
        ]
    )


def excel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Shu hafta", callback_data="xl:w0"),
                InlineKeyboardButton(text="⏮ O'tgan hafta", callback_data="xl:w1"),
            ],
            [
                InlineKeyboardButton(text="🗓 Shu oy", callback_data="xl:m"),
                InlineKeyboardButton(text="♾ Hammasi", callback_data="xl:all"),
            ],
        ]
    )


def restore_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, tiklash", callback_data="rs:yes"),
                InlineKeyboardButton(text="❌ Yo'q", callback_data="rs:no"),
            ]
        ]
    )
