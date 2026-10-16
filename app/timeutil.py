from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def today(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def week_start(d: date) -> date:
    """Haftaning dushanba kuni."""
    return d - timedelta(days=d.weekday())


def week_range(d: date, offset: int = 0) -> tuple[str, str]:
    """(boshlanish, tugash-eksklyuziv) ISO sanalar. offset=1 - o'tgan hafta."""
    start = week_start(d) - timedelta(weeks=offset)
    return start.isoformat(), (start + timedelta(days=7)).isoformat()
