"""Bot xabarlarining yagona dizayni (HTML format).

Qoidalar: sarlavha — qalin, ball va raqamlar — monospace (<code>), vazifa nomi — qalin,
ma'lumot qatorlari — emoji + qalin yorliq. Foydalanuvchi matni har doim esc() dan o'tadi.
"""
from html import escape

LINE = "━━━━━━━━━━━━━━━━"
MAX_SCORE = 10


def esc(value) -> str:
    return escape(str(value), quote=False)


def title(emoji: str, text: str) -> str:
    return f"{emoji} <b>{esc(text)}</b>\n{LINE}"


def kv(emoji: str, label: str, value, code: bool = False) -> str:
    v = f"<code>{esc(value)}</code>" if code else esc(value)
    return f"{emoji} <b>{esc(label)}:</b> {v}"


def quote(text: str) -> str:
    return f"<blockquote>{esc(text)}</blockquote>"


def hint(text: str) -> str:
    return f"<i>{esc(text)}</i>"


def bar(score: float | None, width: int = MAX_SCORE) -> str:
    """Ballni vizual ko'rsatadi: 🟩🟩🟩🟩🟩🟩🟩⬜⬜⬜"""
    if score is None:
        return "⬜" * width
    filled = max(0, min(width, round(score)))
    return "🟩" * filled + "⬜" * (width - filled)


def score_badge(score: int) -> str:
    face = "🏆" if score >= 9 else "👍" if score >= 6 else "📈" if score >= 3 else "💪"
    return f"{face} <code>{score}/{MAX_SCORE}</code>"


def split_lines(lines: list[str], limit: int = 3500) -> list[str]:
    """Uzun matnni satrlar bo'yicha bo'ladi (HTML teglari uzilib qolmasligi uchun)."""
    parts, cur, size = [], [], 0
    for ln in lines:
        if cur and size + len(ln) + 1 > limit:
            parts.append("\n".join(cur))
            cur, size = [], 0
        cur.append(ln)
        size += len(ln) + 1
    if cur:
        parts.append("\n".join(cur))
    return parts
