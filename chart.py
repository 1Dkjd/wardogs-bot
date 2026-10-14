"""Gold bar price card for /chart, styled to match the compare/ammo cards."""
import io
import os
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter, MaxNLocator

from wardogs import RANGES, money

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
plt.rcParams["text.parse_math"] = False  # "$" in prices is literal, not math mode
for f in ("Inter-Medium.otf", "Inter-SemiBold.otf", "Inter-Bold.otf", "InterDisplay-Black.otf"):
    p = os.path.join(FONT_DIR, f)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)

BG, PANEL, LINE = "#121417", "#1c1f24", "#2a2e35"
TEXT, MUTED, DIM = "#eef0f2", "#969ca6", "#696f79"
GOLD, GREEN, RED = "#f0b232", "#57f287", "#ed5b45"
INTER, BLACK = "Inter", "Inter Display"

W, H, DPI = 1000, 600, 72  # dpi 72 -> 1pt == 1px, so sizes below are pixels
RANGE_LABEL = {"7d": "LAST 7 DAYS", "30d": "LAST 30 DAYS", "90d": "LAST 90 DAYS", "all": "ALL TIME"}


def _px(x, y):
    """Pixel coords (top-left origin) -> figure fraction."""
    return x / W, 1 - y / H


def _chip(fig, x, y, text, fg, bg, size=14):
    """Rounded label; x,y = left/vertical-centre in pixels. Returns right edge (px)."""
    t = fig.text(*_px(x + 12, y), text, color=fg, fontsize=size, fontfamily=INTER, fontweight="bold", va="center")
    fig.canvas.draw()
    bb = t.get_window_extent()
    w = bb.width + 24
    fig.patches.append(FancyBboxPatch(_px(x, y + 15), w / W, 30 / H, boxstyle="round,pad=0,rounding_size=0.02",
                                      transform=fig.transFigure, facecolor=bg, edgecolor="none", zorder=-1,
                                      mutation_aspect=W / H))
    return x + w + 10


def _pct_chip(fig, x, y, label, v):
    if v is None:
        return _chip(fig, x, y, f"{label}  n/a", MUTED, PANEL)
    col = GREEN if v < 0 else RED if v > 0 else MUTED
    arrow = "▼" if v < 0 else "▲" if v > 0 else "•"
    return _chip(fig, x, y, f"{label}  {arrow} {abs(v) * 100:.1f}%", col, PANEL)


def render(market, rng="30d", gold_icon=None):
    all_pts = market["points"]
    days = RANGES.get(rng)
    pts = all_pts if not days else [p for p in all_pts if p["t"] >= all_pts[-1]["t"] - days * 86400000]
    xs = [datetime.fromtimestamp(p["t"] / 1000, tz=timezone.utc) for p in pts]
    ys = np.array([p["price"] for p in pts], dtype=float)
    cur = market["stats"]["current"]
    prev = all_pts[-2]["price"] if len(all_pts) > 1 else None
    every = [p["price"] for p in all_pts]
    cheaper_than = sum(1 for v in every if v > cur) / len(every)
    avg30 = float(np.mean(every[-30:]))

    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    fig.patch.set_facecolor(BG)
    fig.patches.append(plt.Rectangle((0, 1 - 5 / H), 1, 5 / H, transform=fig.transFigure, color=GOLD))

    # ---- header ----
    x0 = 32
    if gold_icon is not None:
        ax_i = fig.add_axes([32 / W, 1 - 116 / H, 84 / W, 84 / H])
        ax_i.imshow(np.asarray(gold_icon))
        ax_i.axis("off")
        x0 = 132
    fig.text(*_px(x0, 46), "GOLD BAR EXCHANGE", color=MUTED, fontsize=14, fontfamily=INTER, fontweight="bold", va="center")
    fig.text(*_px(x0 - 2, 86), f"${cur:,}", color=TEXT, fontsize=50, fontfamily=BLACK, fontweight="black", va="center")
    fig.text(*_px(x0, 122), "cash per gold bar", color=DIM, fontsize=15, fontfamily=INTER, va="center")

    # change chips (right side)
    chg = market["stats"]["changes"]
    x = 560
    x = _pct_chip(fig, x, 50, "1D", (cur - prev) / prev if prev else None)
    x = _pct_chip(fig, x, 50, "7D", chg.get("7d"))
    _pct_chip(fig, x, 50, "30D", chg.get("30d"))

    # buy signal
    if cheaper_than >= 0.66:
        sig, col, bg = f"GOOD TIME TO BUY · cheaper than {cheaper_than:.0%} of days", GREEN, "#17301f"
    elif cheaper_than >= 0.33:
        sig, col, bg = f"AVERAGE PRICE · cheaper than {cheaper_than:.0%} of days", GOLD, "#342b17"
    else:
        sig, col, bg = f"EXPENSIVE · pricier than {1 - cheaper_than:.0%} of days", RED, "#33191a"
    _chip(fig, 560, 96, sig, col, bg, size=13)

    # ---- chart ----
    ax = fig.add_axes([32 / W, 78 / H, (W - 120) / W, (H - 238) / H])
    ax.set_facecolor(BG)
    lo_y = max(0, ys.min() - (ys.max() - ys.min() or ys.max()) * 0.15)
    hi_y = ys.max() + (ys.max() - ys.min() or ys.max()) * 0.14
    ax.set_ylim(lo_y, hi_y)
    ax.set_xlim(xs[0], xs[-1])

    # gradient fill under the line
    xn = mdates.date2num(xs)
    grad = np.linspace(0.32, 0, 256).reshape(-1, 1)
    rgba = np.zeros((256, 1, 4))
    rgba[..., :3] = matplotlib.colors.to_rgb(GOLD)
    rgba[..., 3] = grad
    im = ax.imshow(rgba, extent=[xn[0], xn[-1], lo_y, hi_y], aspect="auto", origin="upper", zorder=1)
    poly = ax.fill_between(xs, ys, lo_y, color="none")
    im.set_clip_path(poly.get_paths()[0], transform=ax.transData)

    ax.plot(xs, ys, color=GOLD, linewidth=3, zorder=3, solid_joinstyle="round")
    if len(xs) <= 14:
        ax.scatter(xs, ys, color=GOLD, s=22, zorder=4)

    # 30-day average
    if lo_y < avg30 < hi_y:
        ax.axhline(avg30, color=MUTED, linewidth=1.2, linestyle=(0, (4, 4)), zorder=2)
        ax.text(xs[0], avg30, f"  30-day avg {money(avg30)}", color=MUTED, fontsize=12, fontfamily=INTER,
                va="bottom", ha="left", zorder=5)

    # high / low markers
    i_lo, i_hi = int(ys.argmin()), int(ys.argmax())
    for i, col, dy, lab in ((i_hi, RED, 14, "HIGH"), (i_lo, GREEN, -16, "LOW")):
        ax.scatter([xs[i]], [ys[i]], color=col, s=70, zorder=6, edgecolors=BG, linewidths=2)
        ha = "left" if i < len(xs) * 0.15 else "right" if i > len(xs) * 0.85 else "center"
        ax.annotate(f"{lab} {money(ys[i])}", (xs[i], ys[i]), textcoords="offset points", xytext=(0, dy),
                    ha=ha, va="center", color=col, fontsize=13, fontfamily=INTER, fontweight="bold", zorder=7)

    # current price: glowing dot + price tag on the right axis
    ax.scatter([xs[-1]], [ys[-1]], color=GOLD, s=340, alpha=0.18, zorder=6, linewidths=0)
    ax.scatter([xs[-1]], [ys[-1]], color=GOLD, s=80, zorder=7, edgecolors=BG, linewidths=2.5)
    ax.annotate(money(ys[-1]), xy=(1, ys[-1]), xycoords=("axes fraction", "data"), xytext=(16, 0),
                textcoords="offset points", va="center", ha="left", color=BG, fontsize=13, fontfamily=INTER,
                fontweight="bold", bbox=dict(boxstyle="round,pad=0.35,rounding_size=0.5", fc=GOLD, ec="none"),
                annotation_clip=False, zorder=8)

    # axes styling
    ax.yaxis.tick_right()
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: money(v)))
    ax.yaxis.set_major_locator(MaxNLocator(5))
    loc = mdates.AutoDateLocator(minticks=4, maxticks=8)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.tick_params(colors=DIM, labelsize=12, length=0, pad=10)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_fontfamily(INTER)
    ax.grid(axis="y", color=LINE, linewidth=1)
    for s in ax.spines.values():
        s.set_visible(False)

    # ---- footer ----
    fig.patches.append(plt.Rectangle((32 / W, 38 / H), (W - 64) / W, 1 / H, transform=fig.transFigure, color=LINE))
    xr = _chip(fig, 32, H - 17, RANGE_LABEL.get(rng, rng.upper()), GOLD, "#342b17", size=12)
    fig.text(*_px(xr + 4, H - 17), f"all-time low {money(min(every))}  ·  all-time high {money(max(every))}",
             color=DIM, fontsize=12, fontfamily=INTER, va="center")
    fig.text(*_px(W - 32, H - 17), "data: metaforge.app", color=DIM, fontsize=12, fontfamily=INTER, ha="right", va="center")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG, dpi=DPI)
    plt.close(fig)
    buf.seek(0)
    return buf
