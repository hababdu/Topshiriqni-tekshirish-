import os
from datetime import date

import aiosqlite

from .timeutil import week_range

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    user_id   INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    username  TEXT,
    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
    in_group  INTEGER NOT NULL DEFAULT 1,
    started   INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    week_start  TEXT NOT NULL,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS submissions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    task_id        INTEGER NOT NULL,
    kind           TEXT NOT NULL,
    text           TEXT,
    file_id        TEXT,
    storage_msg_id INTEGER NOT NULL,
    submit_date    TEXT NOT NULL,
    submitted_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    score          INTEGER,
    graded_at      TEXT,
    FOREIGN KEY (user_id) REFERENCES students(user_id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
CREATE INDEX IF NOT EXISTS idx_sub_date ON submissions(submit_date);
CREATE INDEX IF NOT EXISTS idx_sub_user ON submissions(user_id);
"""


class DB:
    def __init__(self, path: str, hidden_ids=frozenset()):
        self.path = path
        # Adminlar (o'qituvchilar) o'quvchilar ro'yxati va statistikaga kirmaydi
        self.hidden = tuple(sorted(int(x) for x in hidden_ids))

    def _not_hidden(self, col: str) -> str:
        if not self.hidden:
            return ""
        return f" AND {col} NOT IN ({','.join(str(i) for i in self.hidden)})"

    async def init(self) -> None:
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        async with aiosqlite.connect(self.path) as c:
            await c.executescript(SCHEMA)
            # Eski bazalar uchun yangi ustunlar (mavjud o'quvchilar: guruhda va botni boshlagan)
            cur = await c.execute("PRAGMA table_info(students)")
            cols = {r[1] for r in await cur.fetchall()}
            if "in_group" not in cols:
                await c.execute("ALTER TABLE students ADD COLUMN in_group INTEGER NOT NULL DEFAULT 1")
            if "started" not in cols:
                await c.execute("ALTER TABLE students ADD COLUMN started INTEGER NOT NULL DEFAULT 1")
            await c.commit()

    # --- yordamchi metodlar ---
    async def _all(self, q: str, args: tuple = ()) -> list[dict]:
        async with aiosqlite.connect(self.path) as c:
            c.row_factory = aiosqlite.Row
            cur = await c.execute(q, args)
            return [dict(r) for r in await cur.fetchall()]

    async def _one(self, q: str, args: tuple = ()) -> dict | None:
        rows = await self._all(q, args)
        return rows[0] if rows else None

    async def _run(self, q: str, args: tuple = ()) -> int:
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
            + " ORDER BY full_name COLLATE NOCASE"
        )

    async def reminder_targets(self) -> list[dict]:
        """Eslatma yuborsa bo'ladigan o'quvchilar (guruhda va botni boshlagan)."""
        return [s for s in await self.all_students() if s["started"]]

    # --- vazifalar ---
    async def add_task(self, title: str, description: str | None, week_start: str) -> int:
        return await self._run(
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
        return await self._run(
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
