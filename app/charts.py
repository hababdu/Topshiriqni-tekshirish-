import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MAX_SCORE = 10
BAR = "#2f6fdb"
GRID = "#d9dde3"


def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def weekly_chart(rows: list[dict], title: str) -> bytes:
    """O'quvchilar bo'yicha haftalik o'rtacha ball (gorizontal diagramma)."""
    rows = rows[:25]
    names = [r["full_name"] for r in rows][::-1]
    avgs = [float(r["avg_score"]) if r["avg_score"] is not None else 0.0 for r in rows][::-1]
    totals = [r["total"] for r in rows][::-1]

    fig, ax = plt.subplots(figsize=(8, max(3.0, 0.45 * len(names) + 1.6)))
    bars = ax.barh(names, avgs, color=BAR)
    ax.set_xlim(0, MAX_SCORE + 2)
    ax.set_xlabel(f"O'rtacha ball (0–{MAX_SCORE})")
    ax.set_title(title, fontsize=12, loc="left")
    ax.grid(axis="x", color=GRID)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for bar, avg, total in zip(bars, avgs, totals):
        ax.text(
            bar.get_width() + 0.15,
            bar.get_y() + bar.get_height() / 2,
            f"{avg:.1f} · {total} ta ish",
            va="center",
            fontsize=8,
        )
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
