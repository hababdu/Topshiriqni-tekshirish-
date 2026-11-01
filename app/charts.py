import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MAX_SCORE = 10
BAR = "#2f6fdb"
GREEN = "#239b72"
RED = "#d9534f"
GRID = "#d9dde3"


def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def weekly_chart(rows: list[dict], title: str, task_stats: list[tuple[str, int, int]] | None = None) -> bytes:
    """Admin uchun: baholangan o'quvchilar reytingi va vazifalar kesimida topshirish holati."""
    ranked = [r for r in rows if r.get("graded", 0) > 0 and r.get("avg_score") is not None][:15]
    ranked = ranked[::-1]

    if task_stats:
        fig, (ax, bx) = plt.subplots(
            1, 2, figsize=(15, max(4.2, 0.38 * max(len(ranked), len(task_stats)) + 2.0)),
            gridspec_kw={"width_ratios": [1.0, 1.15]},
        )
    else:
        fig, ax = plt.subplots(figsize=(8, max(3.0, 0.4 * len(ranked) + 1.8)))
        bx = None

    if ranked:
        names = [r["full_name"][:24] for r in ranked]
        avgs = [float(r["avg_score"]) for r in ranked]
        bars = ax.barh(names, avgs, color=BAR)
        ax.set_xlim(0, MAX_SCORE + 2)
        ax.set_xlabel(f"O'rtacha ball (0–{MAX_SCORE})")
        for bar, avg, r in zip(bars, avgs, ranked):
            ax.text(bar.get_width() + 0.12, bar.get_y() + bar.get_height()/2,
                    f"{avg:.1f} · {r['graded']} ta baho", va="center", fontsize=8)
    else:
        ax.text(0.5, 0.5, "Hali baholangan ish yo'q", ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
    ax.set_title("Eng yaxshi o'quvchilar", fontsize=11, loc="left")
    ax.grid(axis="x", color=GRID)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    if bx is not None:
        if task_stats:
            labels = [x[0][:22] for x in task_stats]
            done = [x[1] for x in task_stats]
            missing = [x[2] for x in task_stats]
            positions = list(range(len(labels)))
            bx.barh(positions, done, color=GREEN, label="Topshirgan")
            bx.barh(positions, missing, left=done, color=RED, label="Topshirmagan")
            bx.set_yticks(positions, labels)
            bx.invert_yaxis()
            bx.set_xlabel("O'quvchilar soni")
            bx.legend(loc="lower right", fontsize=8)
            bx.grid(axis="x", color=GRID)
            bx.set_axisbelow(True)
            for i, (d, m) in enumerate(zip(done, missing)):
                total = d + m
                if total:
                    bx.text(d + m + 0.08, i, f"{d}/{total}", va="center", fontsize=8)
        else:
            bx.text(0.5, 0.5, "Bu davrda vazifa berilmagan", ha="center", va="center", transform=bx.transAxes)
        bx.set_title("Vazifalar bajarilishi", fontsize=11, loc="left")
        for spine in ("top", "right"):
            bx.spines[spine].set_visible(False)

    fig.suptitle(title, fontsize=13, x=0.06, ha="left")
    fig.tight_layout()
    return _to_png(fig)


def progress_chart(series: list[tuple[str, float]], title: str) -> bytes:
    """Bitta o'quvchining haftalar bo'yicha o'rtacha bali (chiziqli diagramma)."""
    labels = [s[0] for s in series]
    values = [s[1] for s in series]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(labels, values, marker="o", color=BAR, linewidth=2)
    ax.set_ylim(0, MAX_SCORE + 0.5)
    ax.set_ylabel("O'rtacha ball")
    ax.set_title(title, fontsize=12, loc="left")
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for x, y in zip(labels, values):
        ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
    return _to_png(fig)
