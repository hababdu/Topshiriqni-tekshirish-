import asyncio
import logging
import os
import re
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiosqlite

from .timeutil import week_range

log = logging.getLogger(__name__)

# {pk} — avtomatik raqamli kalit, {big} — Telegram ID lari uchun katta butun son
SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    user_id   {big} PRIMARY KEY,
    full_name TEXT NOT NULL,
    username  TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    in_group  INTEGER NOT NULL DEFAULT 1,
    started   INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS tasks (
    id          {pk},
    title       TEXT NOT NULL,
    description TEXT,
    week_start  TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS submissions (
    id             {pk},
    user_id        {big} NOT NULL,
    task_id        BIGINT NOT NULL,
    kind           TEXT NOT NULL,
    text           TEXT,
    file_id        TEXT,
    storage_msg_id BIGINT NOT NULL,
    submit_date    TEXT NOT NULL,
    submitted_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    score          INTEGER,
    graded_at      TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES students(user_id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
CREATE INDEX IF NOT EXISTS idx_sub_date ON submissions(submit_date);
CREATE INDEX IF NOT EXISTS idx_sub_user ON submissions(user_id);
"""

# Zaxira / tiklash uchun jadvallar va ustunlar (tartib muhim: bog'liqlik)
TABLE_COLS = {
    "students": ["user_id", "full_name", "username", "joined_at", "in_group", "started"],
    "tasks": ["id", "title", "description", "week_start", "created_at"],
    "submissions": [
        "id", "user_id", "task_id", "kind", "text", "file_id", "storage_msg_id",
        "submit_date", "submitted_at", "score", "graded_at",
    ],
}
TS_COLS = {"joined_at", "created_at", "submitted_at", "graded_at"}
SERIAL_TABLES = {"tasks": "id", "submissions": "id"}

_RETRY_ERRORS: tuple = (OSError, asyncio.TimeoutError)


def _clean_dsn(dsn: str) -> str:
    """Neon ulanish satridagi asyncpg tushunmaydigan parametrlarni olib tashlaydi (channel_binding va h.k.)."""
    parts = urlsplit(dsn)
    keep = [(k, v) for k, v in parse_qsl(parts.query) if k in ("sslmode", "ssl", "application_name")]
    if not any(k in ("sslmode", "ssl") for k, _ in keep):
        keep.append(("sslmode", "require"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(keep), parts.fragment))


def _to_pg(q: str) -> str:
    n = 0

    def repl(_m):
        nonlocal n
        n += 1
        return f"${n}"

    return re.sub(r"\?", repl, q)


def _norm(v):
    if isinstance(v, Decimal):
        return float(v)
    return v


class DB:
    """Ikki rejim: DATABASE_URL berilsa — Postgres (Neon), bo'lmasa — SQLite fayl (lokal sinov uchun)."""

    def __init__(self, path: str, hidden_ids=frozenset(), dsn: str = ""):
        self.path = path
        self.dsn = dsn.strip()
        self.pg = bool(self.dsn)
        self.pool = None
        # Adminlar (o'qituvchilar) o'quvchilar ro'yxati va statistikaga kirmaydi
        self.hidden = tuple(sorted(int(x) for x in hidden_ids))

    def _not_hidden(self, col: str) -> str:
        if not self.hidden:
            return ""
        return f" AND {col} NOT IN ({','.join(str(i) for i in self.hidden)})"

    async def init(self) -> None:
        if self.pg:
            import asyncpg

            global _RETRY_ERRORS
            _RETRY_ERRORS = (
                OSError,
                asyncio.TimeoutError,
                asyncpg.exceptions.ConnectionDoesNotExistError,
                asyncpg.exceptions.InterfaceError,
                asyncpg.exceptions.CannotConnectNowError,
                asyncpg.exceptions.ConnectionFailureError,
            )
            self.pool = await asyncpg.create_pool(
                _clean_dsn(self.dsn),
                min_size=0,
                max_size=5,
                timeout=30,
                command_timeout=30,
                statement_cache_size=0,  # Neon pooler (pgbouncer) bilan mos
                max_inactive_connection_lifetime=60,  # Neon 5 daqiqada uxlaydi — eski ulanishlarni ushlamaymiz
            )
            async with self.pool.acquire() as c:
                await c.execute(SCHEMA.format(pk="BIGSERIAL PRIMARY KEY", big="BIGINT"))
            log.info("Postgres (DATABASE_URL) ga ulandi")
            return
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        async with aiosqlite.connect(self.path) as c:
            await c.executescript(SCHEMA.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT", big="INTEGER"))
            # Eski bazalar uchun yangi ustunlar (mavjud o'quvchilar: guruhda va botni boshlagan)
            cur = await c.execute("PRAGMA table_info(students)")
            cols = {r[1] for r in await cur.fetchall()}
            if "in_group" not in cols:
                await c.execute("ALTER TABLE students ADD COLUMN in_group INTEGER NOT NULL DEFAULT 1")
            if "started" not in cols:
                await c.execute("ALTER TABLE students ADD COLUMN started INTEGER NOT NULL DEFAULT 1")
            await c.commit()
        log.warning("DATABASE_URL yo'q — SQLite (%s) ishlatilyapti. Render'da bu fayl qayta ishga tushganda o'chadi!", self.path)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    # --- yordamchi metodlar ---
    async def _retry(self, fn):
        for attempt in range(3):
            try:
                return await fn()
            except _RETRY_ERRORS as e:
                if not self.pg or attempt == 2:
                    raise
                log.warning("Baza ulanishi xatosi (%s), qayta urinaman...", e)
                await asyncio.sleep(1 + attempt)

    async def _all(self, q: str, args: tuple = ()) -> list[dict]:
        if self.pg:
            async def go():
                async with self.pool.acquire() as c:
                    rows = await c.fetch(_to_pg(q), *args)
                return [{k: _norm(v) for k, v in dict(r).items()} for r in rows]

            return await self._retry(go)
        async with aiosqlite.connect(self.path) as c:
            c.row_factory = aiosqlite.Row
            cur = await c.execute(q, args)
            return [dict(r) for r in await cur.fetchall()]

    async def _one(self, q: str, args: tuple = ()) -> dict | None:
        rows = await self._all(q, args)
        return rows[0] if rows else None

    async def _run(self, q: str, args: tuple = ()) -> None:
        if self.pg:
            async def go():
                async with self.pool.acquire() as c:
                    await c.execute(_to_pg(q), *args)

            await self._retry(go)
            return
        async with aiosqlite.connect(self.path) as c:
            await c.execute(q, args)
            await c.commit()

    async def _insert(self, q: str, args: tuple = ()) -> int:
        """INSERT va yangi qatorning id sini qaytaradi."""
        if self.pg:
            async def go():
                async with self.pool.acquire() as c:
                    return await c.fetchval(_to_pg(q) + " RETURNING id", *args)

            return await self._retry(go)
        async with aiosqlite.connect(self.path) as c:
            cur = await c.execute(q, args)
            await c.commit()
            return cur.lastrowid

    # --- o'quvchilar ---
    async def upsert_member(self, user_id: int, full_name: str, username: str | None) -> None:
        """Guruh a'zosini ro'yxatga qo'shadi (botni hali boshlamagan bo'lishi mumkin)."""
        await self._run(
            "INSERT INTO students(user_id, full_name, username, in_group, started) VALUES(?,?,?,1,0) "
            "ON CONFLICT(user_id) DO UPDATE SET in_group=1, username=excluded.username, "
            "full_name=CASE WHEN students.started=1 THEN students.full_name ELSE excluded.full_name END",
            (user_id, full_name, username),
        )

    async def register_started(self, user_id: int, full_name: str, username: str | None) -> dict:
        """O'quvchi botga /start bosdi (endi unga xabar yuborish mumkin)."""
        await self._run(
            "INSERT INTO students(user_id, full_name, username, in_group, started) VALUES(?,?,?,1,1) "
            "ON CONFLICT(user_id) DO UPDATE SET in_group=1, started=1, username=excluded.username, "
            "full_name=CASE WHEN students.started=1 THEN students.full_name ELSE excluded.full_name END",
            (user_id, full_name, username),
        )
        return await self.get_student(user_id)

    async def mark_left(self, user_id: int) -> None:
        await self._run("UPDATE students SET in_group=0 WHERE user_id=?", (user_id,))

    async def get_student(self, user_id: int) -> dict | None:
        return await self._one("SELECT * FROM students WHERE user_id=?", (user_id,))

    async def all_students(self) -> list[dict]:
        """Hozir guruhda turgan o'quvchilar (adminlarsiz)."""
        return await self._all(
            "SELECT * FROM students WHERE in_group=1" + self._not_hidden("user_id")
            + " ORDER BY lower(full_name)"
        )

    async def reminder_targets(self) -> list[dict]:
        """Eslatma yuborsa bo'ladigan o'quvchilar (guruhda va botni boshlagan)."""
        return [s for s in await self.all_students() if s["started"]]

    # --- vazifalar ---
    async def add_task(self, title: str, description: str | None, week_start: str) -> int:
        return await self._insert(
            "INSERT INTO tasks(title, description, week_start) VALUES(?,?,?)",
            (title, description, week_start),
        )

    async def tasks_for_week(self, week_start: str) -> list[dict]:
        return await self._all(
            "SELECT * FROM tasks WHERE week_start=? ORDER BY id", (week_start,)
        )

    async def get_task(self, task_id: int) -> dict | None:
        return await self._one("SELECT * FROM tasks WHERE id=?", (task_id,))

    # --- topshiriqlar ---
    async def add_submission(
        self,
        user_id: int,
        task_id: int,
        kind: str,
        text: str | None,
        file_id: str | None,
        storage_msg_id: int,
        submit_date: str,
    ) -> int:
        return await self._insert(
            "INSERT INTO submissions(user_id, task_id, kind, text, file_id, storage_msg_id, submit_date) "
            "VALUES(?,?,?,?,?,?,?)",
            (user_id, task_id, kind, text, file_id, storage_msg_id, submit_date),
        )

    async def week_submissions(self, week_start: str) -> dict[int, dict[int, float | None]]:
        """{user_id: {task_id: o'rtacha ball yoki None (hali baholanmagan)}} — shu haftaning vazifalari bo'yicha."""
        rows = await self._all(
            "SELECT sub.user_id, sub.task_id, AVG(sub.score) AS score "
            "FROM submissions sub JOIN tasks t ON t.id=sub.task_id "
            "WHERE t.week_start=? GROUP BY sub.user_id, sub.task_id",
            (week_start,),
        )
        out: dict[int, dict[int, float | None]] = {}
        for r in rows:
            out.setdefault(r["user_id"], {})[r["task_id"]] = r["score"]
        return out

    async def has_submission_on(self, user_id: int, day: date) -> bool:
        row = await self._one(
            "SELECT 1 AS x FROM submissions WHERE user_id=? AND submit_date=? LIMIT 1",
            (user_id, day.isoformat()),
        )
        return row is not None

    async def get_submission(self, sub_id: int) -> dict | None:
        return await self._one(
            "SELECT sub.*, s.full_name, t.title AS task_title FROM submissions sub "
            "JOIN students s ON s.user_id=sub.user_id "
            "JOIN tasks t ON t.id=sub.task_id WHERE sub.id=?",
            (sub_id,),
        )

    async def next_pending(self, after_id: int = 0) -> dict | None:
        return await self._one(
            "SELECT sub.*, s.full_name, t.title AS task_title FROM submissions sub "
            "JOIN students s ON s.user_id=sub.user_id "
            "JOIN tasks t ON t.id=sub.task_id "
            "WHERE sub.score IS NULL AND sub.id>? ORDER BY sub.id LIMIT 1",
            (after_id,),
        )

    async def pending_count(self) -> int:
        row = await self._one("SELECT COUNT(*) AS n FROM submissions WHERE score IS NULL")
        return row["n"] if row else 0

    async def grade(self, sub_id: int, score: int) -> None:
        await self._run(
            "UPDATE submissions SET score=?, graded_at=CURRENT_TIMESTAMP WHERE id=?",
            (score, sub_id),
        )

    # --- statistika ---
    async def week_stats(self, start: str, end: str) -> list[dict]:
        return await self._all(
            "SELECT s.user_id, s.full_name, "
            "COUNT(sub.id) AS total, COUNT(sub.score) AS graded, "
            "COALESCE(SUM(sub.score),0) AS points, AVG(sub.score) AS avg_score "
            "FROM students s LEFT JOIN submissions sub "
            "ON sub.user_id=s.user_id AND sub.submit_date>=? AND sub.submit_date<? "
            "WHERE s.in_group=1" + self._not_hidden("s.user_id") +
            " GROUP BY s.user_id ORDER BY points DESC, total DESC, s.full_name",
            (start, end),
        )

    async def student_summary(self, user_id: int) -> dict:
        row = await self._one(
            "SELECT COUNT(*) AS total, COUNT(score) AS graded, AVG(score) AS avg_score "
            "FROM submissions WHERE user_id=?",
            (user_id,),
        )
        return row or {"total": 0, "graded": 0, "avg_score": None}

    async def student_weekly_series(
        self, user_id: int, today_: date, weeks: int = 8
    ) -> list[tuple[str, float]]:
        """Oxirgi `weeks` hafta bo'yicha o'rtacha ball (eskidan yangiga)."""
        series: list[tuple[str, float]] = []
        for offset in range(weeks - 1, -1, -1):
            start, end = week_range(today_, offset)
            row = await self._one(
                "SELECT AVG(score) AS a FROM submissions "
                "WHERE user_id=? AND submit_date>=? AND submit_date<?",
                (user_id, start, end),
            )
            label = date.fromisoformat(start).strftime("%d.%m")
            series.append((label, float(row["a"]) if row and row["a"] is not None else 0.0))
        return series

    # --- Excel hisobot uchun ---
    async def tasks_in_range(self, start: str, end: str) -> list[dict]:
        """Boshlanish sanasi [start, end) oralig'ida bo'lgan haftalarning vazifalari."""
        return await self._all(
            "SELECT * FROM tasks WHERE week_start>=? AND week_start<? ORDER BY week_start, id",
            (start, end),
        )

    async def score_map(self, task_ids: list[int]) -> dict[int, dict[int, float | None]]:
        """{user_id: {task_id: o'rtacha ball yoki None}} — berilgan vazifalar bo'yicha."""
        if not task_ids:
            return {}
        ids = ",".join(str(int(i)) for i in task_ids)
        rows = await self._all(
            f"SELECT user_id, task_id, AVG(score) AS score FROM submissions "
            f"WHERE task_id IN ({ids}) GROUP BY user_id, task_id"
        )
        out: dict[int, dict[int, float | None]] = {}
        for r in rows:
            out.setdefault(r["user_id"], {})[r["task_id"]] = r["score"]
        return out

    async def submissions_in_range(self, start: str, end: str) -> list[dict]:
        return await self._all(
            "SELECT sub.submit_date, s.full_name, t.title AS task_title, sub.kind, sub.score "
            "FROM submissions sub JOIN students s ON s.user_id=sub.user_id "
            "JOIN tasks t ON t.id=sub.task_id "
            "WHERE sub.submit_date>=? AND sub.submit_date<?" + self._not_hidden("sub.user_id") +
            " ORDER BY sub.submit_date, s.full_name, sub.id",
            (start, end),
        )

    # --- zaxira / tiklash ---
    async def export_all(self) -> dict[str, list[dict]]:
        """Barcha jadvallarning to'liq nusxasi (adminlar va ketganlar ham)."""
        out: dict[str, list[dict]] = {}
        for table, cols in TABLE_COLS.items():
            pk = "user_id" if table == "students" else "id"
            out[table] = await self._all(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {pk}")
        return out

    def _import_value(self, col: str, v):
        if self.pg and col in TS_COLS and isinstance(v, str):
            return datetime.fromisoformat(v)
        return v

    async def import_all(self, tables: dict[str, list[dict]]) -> dict[str, int]:
        """Bazani to'liq almashtiradi (bitta tranzaksiyada: xato bo'lsa eski ma'lumot saqlanadi)."""
        for name in TABLE_COLS:
            if name not in tables or not isinstance(tables[name], list):
                raise ValueError(f"Zaxira faylida «{name}» jadvali yo'q")
        order = ["submissions", "tasks", "students"]  # o'chirish tartibi
        stmts: list[tuple[str, tuple]] = [(f"DELETE FROM {t}", ()) for t in order]
        for table, cols in TABLE_COLS.items():
            ph = ",".join("?" for _ in cols)
            sql = f"INSERT INTO {table}({', '.join(cols)}) VALUES({ph})"
            for row in tables[table]:
                stmts.append((sql, tuple(self._import_value(c, row.get(c)) for c in cols)))
        counts = {t: len(tables[t]) for t in TABLE_COLS}

        if self.pg:
            async def go():
                async with self.pool.acquire() as c:
                    async with c.transaction():
                        for sql, args in stmts:
                            await c.execute(_to_pg(sql), *args)
                        for table, col in SERIAL_TABLES.items():
                            await c.execute(
                                f"SELECT setval(pg_get_serial_sequence('{table}','{col}'), "
                                f"COALESCE((SELECT MAX({col}) FROM {table}), 0) + 1, false)"
                            )

            await self._retry(go)
            return counts
        async with aiosqlite.connect(self.path) as c:
            try:
                for sql, args in stmts:
                    await c.execute(sql, args)
                await c.commit()
            except Exception:
                await c.rollback()
                raise
        return counts
