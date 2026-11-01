"""Admin hisobotlari uchun PNG diagrammalar."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MAX_SCORE = 10
BLUE = "#4568DC"
GREEN = "#20A779"
RED = "#E35D6A"
INK = "#202A3A"
MUTED = "#748094"
GRID = "#E8ECF2"
BG = "#FFFFFF"


def _save(fig) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=180, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return buffer.getvalue()


def _style(ax) -> None:
    ax.set_facecolor(BG)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="both", colors=MUTED, labelsize=9, length=0, pad=7)


def ranking_chart(rows: list[dict], title: str) -> bytes:
    """TOP-10: avval jami ball, keyin o'rtacha ball va baholangan vazifalar."""
    ranked = [r for r in rows if int(r.get("graded") or 0) > 0 and r.get("avg_score") is not None]
    ranked.sort(
        key=lambda r: (
            float(r.get("points") or 0),
            float(r.get("avg_score") or 0),
            int(r.get("graded") or 0),
            str(r.get("full_name") or "").casefold(),
        ),
        reverse=True,
    )
    ranked = ranked[:10]
    fig_h = max(4.0, 0.48 * len(ranked) + 1.9)
    fig, ax = plt.subplots(figsize=(10.5, fig_h))
    fig.subplots_adjust(left=0.27, right=0.91, top=0.82, bottom=0.13)
    fig.text(0.055, 0.94, "ENG YAXSHI O‘QUVCHILAR", fontsize=16, weight="bold", color=INK)
    fig.text(0.055, 0.885, title, fontsize=9, color=MUTED)

    if ranked:
        names = [str(r["full_name"])[:28] for r in ranked]
        points = [float(r.get("points") or 0) for r in ranked]
        avgs = [float(r["avg_score"]) for r in ranked]
        colors = ["#D6A84B" if i == 0 else "#AEB8C7" if i == 1 else "#B77A52" if i == 2 else BLUE for i in range(len(ranked))]
        bars = ax.barh(range(len(names)), points, color=colors, height=0.62, edgecolor="none")
        ax.set_yticks(range(len(names)), names)
        ax.set_xlabel("Jami ball", color=MUTED, fontsize=9, labelpad=10)
        ax.set_xlim(0, max(points) * 1.28 if max(points) else 1)
        for i, (bar, p, avg) in enumerate(zip(bars, points, avgs)):
            ax.text(bar.get_width() + max(points or [1]) * .025, bar.get_y() + bar.get_height()/2,
                    f"{p:g} ball  ·  o‘rtacha {avg:.1f}/10", va="center", fontsize=8.5, color=INK)
        ax.invert_yaxis()
        _style(ax)
        ax.grid(axis="y", visible=False)
        ax.text(0.0, -0.12, "Reyting tartibi: jami ball → o‘rtacha baho → baholangan vazifalar",
                transform=ax.transAxes, fontsize=8, color=MUTED)
    else:
        ax.axis("off")
        ax.text(.5, .5, "Bu davrda baholangan topshiriqlar yo‘q", ha="center", va="center", color=MUTED, fontsize=12)
    return _save(fig)


def lesson_completion_chart(task_stats: list[tuple[str, int, int]], title: str) -> bytes:
    """Har bir vazifa bo'yicha topshirgan va topshirmaganlar soni."""
    stats = task_stats[:18]
    fig_h = max(4.0, 0.48 * len(stats) + 1.9)
    fig, ax = plt.subplots(figsize=(10.5, fig_h))
    fig.subplots_adjust(left=0.27, right=0.91, top=0.82, bottom=0.22)
    fig.text(0.055, 0.94, "DARSLAR BO‘YICHA BAJARILISH", fontsize=16, weight="bold", color=INK)
    fig.text(0.055, 0.885, title, fontsize=9, color=MUTED)
    if stats:
        labels = [str(x[0])[:30] for x in stats][::-1]
        done = [max(0, int(x[1])) for x in stats][::-1]
        missing = [max(0, int(x[2])) for x in stats][::-1]
        y = list(range(len(stats)))
        ax.barh(y, done, color=GREEN, height=.62, label="Topshirgan", edgecolor="none")
        ax.barh(y, missing, left=done, color=RED, height=.62, label="Topshirmagan", edgecolor="none")
        ax.set_yticks(y, labels)
        total_max = max([d + m for d, m in zip(done, missing)] or [1])
        ax.set_xlim(0, max(1, total_max * 1.20))
        ax.set_xlabel("O‘quvchilar soni", color=MUTED, fontsize=9, labelpad=10)
        for i, (d, m) in enumerate(zip(done, missing)):
            if d:
                ax.text(d/2, i, str(d), va="center", ha="center", color="white", fontsize=8, weight="bold")
            if m:
                ax.text(d + m/2, i, str(m), va="center", ha="center", color="white", fontsize=8, weight="bold")
            ax.text(d + m + total_max*.025, i, f"{d}/{d+m}", va="center", color=INK, fontsize=8)
        ax.legend(loc="upper right", bbox_to_anchor=(1.0, 1.02), frameon=False, ncol=2, fontsize=8)
        _style(ax)
        ax.grid(axis="y", visible=False)
    else:
        ax.axis("off")
        ax.text(.5, .5, "Tanlangan davrda vazifa berilmagan", ha="center", va="center", color=MUTED, fontsize=12)
    return _save(fig)


def overall_progress_chart(submitted: int, missing: int, title: str) -> bytes:
    """Barcha vazifa-o'quvchi juftliklari bo'yicha bajarilish ulushi."""
    submitted = max(0, int(submitted))
    missing = max(0, int(missing))
    total = submitted + missing
    percent = (submitted / total * 100) if total else 0.0
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    fig.subplots_adjust(left=.08, right=.92, top=.82, bottom=.20)
    fig.text(.07, .94, "UMUMIY O‘QUV JARAYONI", fontsize=16, weight="bold", color=INK)
    fig.text(.07, .885, title, fontsize=9, color=MUTED)
    if total:
        wedges, _ = ax.pie(
            [submitted, missing], startangle=90, counterclock=False,
            colors=[GREEN, RED], wedgeprops={"width": .30, "edgecolor": BG, "linewidth": 4},
        )
        ax.text(0, .08, f"{percent:.1f}%", ha="center", va="center", fontsize=27, weight="bold", color=INK)
        ax.text(0, -.19, "topshirilgan", ha="center", va="center", fontsize=10, color=MUTED)
        ax.legend(wedges, [f"Topshirgan  ·  {submitted}", f"Topshirmagan  ·  {missing}"],
                  loc="lower center", bbox_to_anchor=(.5, -.10), ncol=2, frameon=False, fontsize=9)
        fig.text(.5, .12, f"Jami rejalashtirilgan topshiriq: {total}", ha="center", fontsize=9, color=MUTED)
    else:
        ax.text(0, 0, "Hisoblash uchun vazifa yoki o‘quvchi yo‘q", ha="center", va="center", color=MUTED, fontsize=11)
        ax.set_xlim(-1, 1)
        ax.set_ylim(-1, 1)
    ax.set_aspect("equal")
    return _save(fig)
