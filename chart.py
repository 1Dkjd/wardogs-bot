"""Renders the MetaForge gold price history as a PNG for Discord."""
import io
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from wardogs import money

BG, PANEL, GRID, TEXT, MUTED = "#2b2d31", "#2b2d31", "#3f4147", "#f2f3f5", "#b5bac1"
GOLD, GREEN, RED = "#f0b232", "#57f287", "#ed4245"


def render(points, label):
    xs = [datetime.fromtimestamp(p["t"] / 1000, tz=timezone.utc) for p in points]
    ys = [p["price"] for p in points]

    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=120)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    ax.plot(xs, ys, color=GOLD, linewidth=2.2, marker="o" if len(xs) <= 10 else None, markersize=3)
    pad = (max(ys) - min(ys)) or max(ys)
    floor = max(0, min(ys) - pad * 0.18)
    ax.fill_between(xs, ys, floor, color=GOLD, alpha=0.12)

    lo, hi = ys.index(min(ys)), ys.index(max(ys))
    ax.scatter([xs[lo]], [ys[lo]], color=GREEN, s=40, zorder=5)
    ax.scatter([xs[hi]], [ys[hi]], color=RED, s=40, zorder=5)
    ax.scatter([xs[-1]], [ys[-1]], color=GOLD, s=60, zorder=6, edgecolors=BG, linewidths=2)
    ax.annotate(f"low {money(ys[lo])}", (xs[lo], ys[lo]), textcoords="offset points", xytext=(0, -16),
                ha="center", color=GREEN, fontsize=9, fontweight="bold")
    ax.annotate(f"high {money(ys[hi])}", (xs[hi], ys[hi]), textcoords="offset points", xytext=(0, 8),
                ha="center", color=RED, fontsize=9, fontweight="bold")

    ax.set_title(f"WARDOGS gold bar price — {label}", color=TEXT, fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: money(v)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_ylim(bottom=floor, top=max(ys) + pad * 0.15)
    fig.text(0.99, 0.01, "data: metaforge.app", color=MUTED, fontsize=8, ha="right")

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    buf.seek(0)
    return buf
