"""Pillow-rendered image cards for /ammo and /compare."""
import io
import os

from PIL import Image, ImageDraw, ImageFont

from wardogs import ROUND_SHORT

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")

BG = (18, 20, 23)
PANEL = (28, 31, 36)
CELL = (35, 39, 45)
LINE = (52, 57, 65)
TEXT = (238, 240, 242)
MUTED = (150, 156, 166)
DIM = (105, 111, 121)
GOLD = (240, 178, 50)

ROUND_NAMES = {"FMJ": "Standard", "HollowPoint": "Flesh Damage", "ArmorPiercing": "Armor Piercing"}
ROUND_ACCENT = {"FMJ": (180, 186, 196), "HollowPoint": (237, 91, 69), "ArmorPiercing": (88, 166, 255)}


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


F = {
    "title": _font("InterDisplay-Black.otf", 52),
    "big": _font("InterDisplay-Black.otf", 40),
    "h": _font("Inter-Bold.otf", 22),
    "b": _font("Inter-SemiBold.otf", 18),
    "m": _font("Inter-Medium.otf", 16),
    "s": _font("Inter-SemiBold.otf", 13),
}


def stk_color(n):
    """MetaForge's shots-to-kill scale: fewer shots = greener."""
    if n is None:
        return DIM
    for limit, col in ((1, (87, 242, 135)), (2, (139, 227, 107)), (4, (199, 224, 79)), (8, (240, 178, 50)),
                       (12, (240, 138, 50)), (19, (237, 91, 69))):
        if n <= limit:
            return col
    return (194, 58, 58)


def _rr(d, box, fill=None, outline=None, r=12, w=2):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=w)


def _fit(img, max_w, max_h):
    img = img.convert("RGBA")
    s = min(max_w / img.width, max_h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


def _paste_center(base, img, cx, cy):
    base.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def _chip(d, x, y, text, fill=CELL, color=TEXT, font=None):
    font = font or F["s"]
    w = d.textlength(text, font=font)
    _rr(d, (x, y, x + w + 20, y + 28), fill=fill, r=14)
    d.text((x + 10, y + 14), text, font=font, fill=color, anchor="lm")
    return x + w + 28


def _winners(scores):
    """Indexes with the best (lowest) score. Empty when everything ties, so no fake 'best'."""
    vals = [v for v in scores if v is not None]
    if len(vals) < 2:
        return set()
    top = min(vals)
    win = {i for i, v in enumerate(scores) if v == top}
    return set() if len(win) == len(vals) else win


def _armor_rows(b, zone):
    rows = [("NO ARMOR", None)]
    for a in b.armour_for_zone(zone):
        kind = "HELMET" if a["slot"] == "helmet" else "ARMOR"
        rows.append((f"LEVEL {a['name'].split()[1]} {kind}", a))
    return rows


def _header(img, d, b, w, icon, zone, rng, width, subtitle_extra="", ctx=None):
    cal = b.calibre(w)
    # weapon icon panel
    _rr(d, (32, 32, 272, 168), fill=PANEL, r=14)
    if icon:
        _paste_center(img, _fit(icon, 210, 116), 152, 100)
    d.text((300, 40), w["name"].upper(), font=F["title"], fill=TEXT)
    sub = f"{cal.get('label', '?')} · {w.get('weaponClass') or w.get('subcategory', '')}{subtitle_extra}"
    d.text((302, 104), sub, font=F["b"], fill=MUTED)
    x = 300
    pellets = cal.get("pellets") or 1
    chips = [f"{cal.get('baseDamage', '?')}{f'×{pellets}' if pellets > 1 else ''} DMG",
             f"{w['roundsPerMinute']:g} RPM" if w.get("roundsPerMinute") else None,
             f"{w['muzzleVelocity']} M/S" if w.get("muzzleVelocity") else None,
             f"{w['magSize']} RND" if w.get("magSize") else None]
    for t in filter(None, chips):
        x = _chip(d, x, 136, t)
    ctx = ctx or f"{b.zones[zone].upper()} · {rng} M"
    tw = d.textlength(ctx, font=F["s"])
    _chip(d, width - 32 - tw - 20, 44, ctx, fill=(52, 44, 22), color=GOLD)


def _footer(d, width, height, b):
    d.line((32, height - 44, width - 32, height - 44), fill=LINE, width=1)
    d.text((32, height - 24), f"{b.health} HP target  ·  * plate breaks before the kill  ·  TTK includes bullet travel",
           font=F["s"], fill=DIM, anchor="lm")
    d.text((width - 32, height - 24), "data: metaforge.app", font=F["s"], fill=DIM, anchor="rm")


SHELL_ACCENT = {"BUCK": (240, 178, 50), "SLUG": (88, 166, 255)}


def ammo_card(b, w, zone, rng, weapon_icon=None, round_icons=None):
    """round_icons: {option short name: PIL image}."""
    round_icons = round_icons or {}
    opts = b.ammo_options(w)
    rows = _armor_rows(b, zone)

    W, label_w, pad = 1000, 190, 32
    col_w = (W - 2 * pad - label_w) / len(opts)
    head_h, colhead_h, row_h, mod_h = 196, 112, 82, 186
    H = head_h + colhead_h + row_h * len(rows) + mod_h + 64

    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 5), fill=GOLD)
    _header(img, d, b, w, weapon_icon, zone, rng, W)

    # column headers
    y0 = head_h
    for i, o in enumerate(opts):
        x = pad + label_w + i * col_w
        accent = ROUND_ACCENT.get(o["rnd"], TEXT) if o["short"] not in SHELL_ACCENT else SHELL_ACCENT[o["short"]]
        if o["short"] in round_icons and round_icons[o["short"]]:
            _paste_center(img, _fit(round_icons[o["short"]], 64, 64), x + 44, y0 + 44)
        d.text((x + 86, y0 + 30), o["short"], font=F["big"], fill=accent, anchor="lm")
        d.text((x + 88, y0 + 64), o["name"], font=F["m"], fill=MUTED, anchor="lm")
        d.line((x + 12, y0 + colhead_h - 14, x + col_w - 12, y0 + colhead_h - 14), fill=accent, width=3)

    # grid
    y = y0 + colhead_h
    for label, armor in rows:
        hits = [b.hit(w, o["rnd"], zone, armor, rng, o["cal"]) for o in opts]
        best = _winners([(h["shots"], h["ttk"] or 0) if h else None for h in hits])
        d.text((pad, y + row_h / 2 - 9), label, font=F["b"], fill=TEXT, anchor="lm")
        if armor:
            d.text((pad, y + row_h / 2 + 14), f"blocks {armor['reduction']}% · {armor['durability']} dur",
                   font=F["s"], fill=DIM, anchor="lm")
        for i, h in enumerate(hits):
            x = pad + label_w + i * col_w
            box = (x + 8, y + 6, x + col_w - 8, y + row_h - 6)
            _rr(d, box, fill=CELL, outline=GOLD if i in best else None, r=12, w=2)
            if not h:
                d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), "—", font=F["h"], fill=DIM, anchor="mm")
                continue
            col = stk_color(h["shots"])
            num = f"{h['shots']}{'*' if h['breaks'] else ''}"
            d.text((box[0] + 18, (box[1] + box[3]) / 2 - 1), num, font=F["big"], fill=col, anchor="lm")
            nx = box[0] + 22 + d.textlength(num, font=F["big"])
            d.text((nx, (box[1] + box[3]) / 2 - 10), "SHOTS" if h["shots"] != 1 else "SHOT", font=F["s"], fill=MUTED, anchor="lm")
            d.text((nx, (box[1] + box[3]) / 2 + 10), f"{h['ttk']:.2f}s" if h["ttk"] is not None else "", font=F["s"], fill=DIM, anchor="lm")
            d.text((box[2] - 16, (box[1] + box[3]) / 2 - 10), f"{h['dmg']:.0f}", font=F["h"], fill=TEXT, anchor="rm")
            d.text((box[2] - 16, (box[1] + box[3]) / 2 + 13), "DMG/HIT", font=F["s"], fill=DIM, anchor="rm")
            if i in best:
                tw = d.textlength("BEST", font=F["s"])
                _rr(d, (box[2] - tw - 30, box[1] - 10, box[2] - 10, box[1] + 10), fill=GOLD, r=10)
                d.text((box[2] - 20, box[1]), "BEST", font=F["s"], fill=BG, anchor="rm")
        y += row_h

    # modifiers
    y += 18
    _rr(d, (pad, y, W - pad, y + mod_h - 6), fill=PANEL, r=14)
    covering = b.armour_for_zone(zone)
    tier = covering[0]["tier"] if covering else "Armor.Medium"
    cals = [b.calibres.get(o["cal"], {}) for o in opts]
    combats = [b.combat(c, o["rnd"]) for c, o in zip(cals, opts)]
    labels = [("vs flesh", lambda c, cal: f"{c['bare']:.0%}"),
              ("vs armor", lambda c, cal: f"{c['vsTier'].get(tier, 1):.0%}"),
              ("armor blocks", lambda c, cal: f"×{c['penScalar']:g}"),
              ("plate wear / hit", lambda c, cal: f"{cal.get('baseDamage', 0) * (cal.get('pellets') or 1) * c['plateArmor']:.0f} dur")]
    if any((c.get("pellets") or 1) > 1 for c in cals):
        labels.insert(0, ("pellets", lambda c, cal: f"{cal.get('pellets') or 1}"))
    d.text((pad + 20, y + 22), "ROUND MODIFIERS", font=F["s"], fill=MUTED, anchor="lm")
    for li, (name, fn) in enumerate(labels[:5]):
        ly = y + 52 + li * 24
        d.text((pad + 20, ly), name, font=F["m"], fill=DIM, anchor="lm")
        for i, (c, cal) in enumerate(zip(combats, cals)):
            cx = pad + label_w + i * col_w + col_w / 2
            d.text((cx, ly), fn(c, cal), font=F["b"], fill=TEXT, anchor="mm")

    _footer(d, W, H, b)
    return _png(img)


def compare_card(b, weapons, rnd, zone, rng, icons=None):
    icons = icons or {}
    rows = _armor_rows(b, zone)
    W, pad, label_w = 1000, 32, 190
    col_w = (W - 2 * pad - label_w) / len(weapons)
    stat_rows = [
        ("Calibre", lambda w: b.calibre(w).get("label", "?"), None),
        ("Base damage", lambda w: (f"{b.calibre(w).get('baseDamage')} ×{b.calibre(w)['pellets']}"
                                   if (b.calibre(w).get("pellets") or 1) > 1 else b.calibre(w).get("baseDamage")), "hi"),
        ("Fire rate", lambda w: w.get("roundsPerMinute"), "hi"),
        ("Velocity", lambda w: w.get("muzzleVelocity"), "hi"),
        ("Eff. range", lambda w: w.get("effectiveRange"), "hi"),
        ("Magazine", lambda w: w.get("magSize"), "hi"),
        ("Accuracy", lambda w: w.get("accuracyMoa"), "lo"),
    ]
    units = {"Fire rate": " rpm", "Velocity": " m/s", "Eff. range": " m", "Accuracy": " MOA"}
    head_h, stat_h, row_h = 210, 34, 72
    H = 40 + head_h + stat_h * len(stat_rows) + 70 + row_h * len(rows) + 70

    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 5), fill=GOLD)

    # title row
    d.text((pad, 44), "  vs  ".join(w["name"].upper() for w in weapons), font=F["h"], fill=TEXT, anchor="lm")
    ctx = f"{ROUND_SHORT.get(rnd, rnd)} · {b.zones[zone].upper()} · {rng} M"
    tw = d.textlength(ctx, font=F["s"])
    _chip(d, W - pad - tw - 20, 30, ctx, fill=(52, 44, 22), color=GOLD)

    # weapon panels
    y0 = 76
    for i, w in enumerate(weapons):
        x = pad + label_w + i * col_w
        _rr(d, (x + 8, y0, x + col_w - 8, y0 + head_h - 20), fill=PANEL, r=14)
        if icons.get(w["slug"]):
            _paste_center(img, _fit(icons[w["slug"]], col_w - 50, 100), x + col_w / 2, y0 + 64)
        d.text((x + col_w / 2, y0 + 140), w["name"].upper(), font=F["h"], fill=TEXT, anchor="mm")
        used = b.effective_round(w, rnd)
        if used != rnd:
            d.text((x + col_w / 2, y0 + 166), f"no {ROUND_SHORT.get(rnd, rnd)} ammo · using {ROUND_SHORT.get(used, used)}",
                   font=F["s"], fill=GOLD, anchor="mm")
        else:
            d.text((x + col_w / 2, y0 + 166), w.get("weaponClass") or w.get("subcategory", ""), font=F["s"], fill=MUTED, anchor="mm")

    # stats with winner highlighted
    y = y0 + head_h
    for li, (name, fn, better) in enumerate(stat_rows):
        if li % 2 == 0:
            d.rectangle((pad, y, W - pad, y + stat_h), fill=(23, 25, 29))
        d.text((pad + 12, y + stat_h / 2), name, font=F["m"], fill=MUTED, anchor="lm")
        vals = [fn(w) for w in weapons]
        nums = [v for v in vals if isinstance(v, (int, float))]
        win = None
        if better and len(nums) == len(vals) and len(set(nums)) > 1:
            win = max(nums) if better == "hi" else min(nums)
        for i, v in enumerate(vals):
            cx = pad + label_w + i * col_w + col_w / 2
            txt = "—" if v is None else f"{v:g}{units.get(name, '')}" if isinstance(v, (int, float)) else str(v)
            d.text((cx, y + stat_h / 2), txt, font=F["b"], fill=GOLD if win is not None and v == win else TEXT, anchor="mm")
        y += stat_h

    # shots to kill
    y += 28
    d.text((pad, y + 10), f"SHOTS TO KILL · {ROUND_SHORT.get(rnd, rnd)} ROUNDS", font=F["s"], fill=MUTED, anchor="lm")
    y += 30
    for label, armor in rows:
        hits = [b.hit(w, rnd, zone, armor, rng) for w in weapons]
        best = _winners([h["ttk"] if h and h["ttk"] is not None else None for h in hits])
        d.text((pad, y + row_h / 2), label, font=F["b"], fill=TEXT, anchor="lm")
        for i, h in enumerate(hits):
            x = pad + label_w + i * col_w
            box = (x + 8, y + 5, x + col_w - 8, y + row_h - 5)
            _rr(d, box, fill=CELL, outline=GOLD if i in best else None, r=12)
            mid = (box[1] + box[3]) / 2
            if not h:
                d.text(((box[0] + box[2]) / 2, mid), "—", font=F["h"], fill=DIM, anchor="mm")
                continue
            num = f"{h['shots']}{'*' if h['breaks'] else ''}"
            d.text((box[0] + 18, mid), num, font=F["big"], fill=stk_color(h["shots"]), anchor="lm")
            nx = box[0] + 22 + d.textlength(num, font=F["big"])
            d.text((nx, mid - 9), "SHOTS" if h["shots"] != 1 else "SHOT", font=F["s"], fill=MUTED, anchor="lm")
            d.text((nx, mid + 10), f"{h['dmg']:.0f} dmg", font=F["s"], fill=DIM, anchor="lm")
            d.text((box[2] - 16, mid - 9), f"{h['ttk']:.2f}s" if h["ttk"] is not None else "", font=F["h"], fill=TEXT, anchor="rm")
            d.text((box[2] - 16, mid + 13), "TTK", font=F["s"], fill=DIM, anchor="rm")
        y += row_h

    _footer(d, W, H, b)
    return _png(img)


def _png(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf


GOOD, BAD = (87, 242, 135), (237, 91, 69)


def _pct_chip(d, x, y, label, mult, lower_is_better=True):
    """Chip like 'V -30%' coloured by whether the change helps. Returns new x."""
    if abs(mult - 1) < 0.005:
        return x
    pct = (mult - 1) * 100
    good = (pct < 0) == lower_is_better
    col = GOOD if good else BAD
    return _chip(d, x, y, f"{label} {pct:+.0f}%", fill=(25, 44, 32) if good else (48, 26, 26), color=col)


def weapon_card(b, A, w, weapon_icon=None, att_icons=None):
    """Recoil card: spray pattern stock vs best build, plus the best recoil attachment per slot."""
    from wardogs import spray_path

    att_icons = att_icons or {}
    build = A.best_recoil_build(w)
    stock, best = spray_path(w), spray_path(w, build["v"], build["h"])
    rows = build["slots"]

    W, pad = 1000, 32
    head_h, panel_top = 196, 196
    row_h = 92
    panel_h = max(430, 70 + row_h * max(1, len(rows)) + 20)
    H = panel_top + panel_h + 20 + 50 + 66

    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 5), fill=GOLD)
    _header(img, d, b, w, weapon_icon, None, None, W, ctx="BEST FOR RECOIL")

    # ---- spray pattern panel ----
    L, T, R, B = pad, panel_top, pad + 420, panel_top + panel_h
    _rr(d, (L, T, R, B), fill=PANEL, r=14)
    shots = len(stock) - 1
    d.text((L + 20, T + 24), f"SPRAY PATTERN · {shots} SHOTS" if shots > 1 else "SPRAY PATTERN", font=F["s"], fill=MUTED, anchor="lm")
    improved = abs(build["v"] - 1) > 0.005 or abs(build["h"] - 1) > 0.005
    if len(stock) > 2:
        climb = max(1e-6, max(p[1] for p in stock))
        X_EXAG = 3  # widen horizontal drift so it's visible
        plot_top, plot_bot = T + 70, B - 70
        sc = (plot_bot - plot_top) / climb
        cx = (L + R) / 2

        def pt(p):
            return (cx + p[0] * sc * X_EXAG, plot_bot - p[1] * sc)

        # grid every 5 degrees
        step = 5 if climb > 12 else 2
        for deg in range(0, int(climb) + 1, step):
            y = plot_bot - deg * sc
            d.line((L + 50, y, R - 20, y), fill=(40, 44, 51), width=1)
            d.text((L + 42, y), f"{deg}°", font=F["s"], fill=DIM, anchor="rm")
        d.line((cx, plot_top - 10, cx, plot_bot + 8), fill=(48, 53, 61), width=1)
        paths = ((stock, (120, 126, 136), 3), (best, GOLD, 4)) if improved else ((stock, GOLD, 4),)
        for path, col, r_dot in paths:
            pts = [pt(p) for p in path]
            d.line(pts, fill=col, width=3, joint="curve")
            for q in pts[1:]:
                d.ellipse((q[0] - r_dot, q[1] - r_dot, q[0] + r_dot, q[1] + r_dot), fill=col)
        # crosshair at aim point
        o = pt((0, 0))
        d.ellipse((o[0] - 7, o[1] - 7, o[0] + 7, o[1] + 7), outline=TEXT, width=2)
        # end labels
        se, be = pt(stock[-1]), pt(best[-1])
        if improved:
            d.text((se[0] + 12, se[1]), f"{stock[-1][1]:.1f}°", font=F["b"], fill=(150, 156, 166), anchor="lm")
        d.text((be[0] + 12, be[1]), f"{best[-1][1]:.1f}°", font=F["b"], fill=GOLD, anchor="lm")
        # legend
        ly = B - 36
        if improved:
            d.line((L + 20, ly, L + 44, ly), fill=(120, 126, 136), width=3)
            d.text((L + 52, ly), "Stock", font=F["s"], fill=MUTED, anchor="lm")
            d.line((L + 110, ly, L + 134, ly), fill=GOLD, width=3)
            d.text((L + 142, ly), "Best build", font=F["s"], fill=GOLD, anchor="lm")
        else:
            d.text((L + 20, ly), "Climb per spray", font=F["s"], fill=MUTED, anchor="lm")
        d.text((R - 20, ly), "width ×3", font=F["s"], fill=DIM, anchor="rm")
    else:
        d.text(((L + R) / 2, (T + B) / 2 - 12), "No spray pattern", font=F["h"], fill=MUTED, anchor="mm")
        d.text(((L + R) / 2, (T + B) / 2 + 16), "single-shot weapon, recoil applies per shot", font=F["s"], fill=DIM, anchor="mm")

    # ---- best attachments panel ----
    L2, R2 = R + 20, W - pad
    _rr(d, (L2, T, R2, B), fill=PANEL, r=14)
    d.text((L2 + 20, T + 24), "BEST ATTACHMENTS FOR RECOIL", font=F["s"], fill=MUTED, anchor="lm")
    y = T + 52
    if not rows:
        d.text(((L2 + R2) / 2, (T + B) / 2), "No recoil attachments for this weapon", font=F["b"], fill=MUTED, anchor="mm")
    for row in rows:
        p = row["pick"]
        box = (L2 + 14, y, R2 - 14, y + row_h - 10)
        _rr(d, box, fill=CELL, r=12)
        ic = att_icons.get(p["slug"]) if p else None
        _rr(d, (box[0] + 10, box[1] + 10, box[0] + 72, box[3] - 10), fill=(28, 31, 36), r=10)
        if ic:
            _paste_center(img, _fit(ic, 54, 54), box[0] + 41, (box[1] + box[3]) / 2)
        tx = box[0] + 86
        d.text((tx, box[1] + 18), row["label"].upper(), font=F["s"], fill=DIM, anchor="lm")
        if p:
            d.text((tx, box[1] + 40), p["name"], font=F["b"], fill=TEXT, anchor="lm")
            cx2 = tx
            cx2 = _pct_chip(d, cx2, box[1] + 54, "VERT", p["v"])
            cx2 = _pct_chip(d, cx2, box[1] + 54, "HORIZ", p["h"])
            cx2 = _pct_chip(d, cx2, box[1] + 54, "ADS", p["ads"])
            if p.get("capacity_delta"):
                cd = p["capacity_delta"]
                _chip(d, cx2, box[1] + 54, f"{cd:+d} RND", fill=(48, 26, 26) if cd < 0 else (25, 44, 32),
                      color=BAD if cd < 0 else GOOD)
            if p.get("alt"):
                d.text((box[2] - 14, box[1] + 18), f"or {p['alt']['name']} for horizontal",
                       font=F["s"], fill=DIM, anchor="rm")
        else:
            d.text((tx, box[1] + 42), "Keep stock", font=F["b"], fill=MUTED, anchor="lm")
            d.text((tx, box[1] + 64), "no option here improves recoil", font=F["s"], fill=DIM, anchor="lm")
        y += row_h

    # ---- totals ----
    ty = B + 20
    _rr(d, (pad, ty, W - pad, ty + 50), fill=PANEL, r=14)
    d.text((pad + 20, ty + 25), "FULL BUILD", font=F["s"], fill=MUTED, anchor="lm")
    x = pad + 120
    for label, mult in (("VERTICAL RECOIL", build["v"]), ("HORIZONTAL", build["h"]), ("SPREAD", build["spread"]),
                        ("ADS TIME", build["ads"])):
        nx = _pct_chip(d, x, ty + 11, label, mult)
        x = nx if nx != x else x
    if x == pad + 120:
        d.text((x, ty + 25), "stock is already as steady as it gets", font=F["s"], fill=DIM, anchor="lm")

    d.line((pad, H - 44, W - pad, H - 44), fill=LINE, width=1)
    d.text((pad, H - 24), "Optics skipped (no recoil effect)  ·  vertical weighted 60%, horizontal 40%",
           font=F["s"], fill=DIM, anchor="lm")
    d.text((W - pad, H - 24), "data: metaforge.app", font=F["s"], fill=DIM, anchor="rm")
    return _png(img)


# ---------------- gold / cost cards ----------------
def _money(n):
    from wardogs import money
    return money(n)


def _signal(market):
    every = [p["price"] for p in market["points"]]
    cur = market["stats"]["current"]
    cheaper = sum(1 for v in every if v > cur) / len(every)
    if cheaper >= 0.66:
        return f"GOOD TIME TO BUY · cheaper than {cheaper:.0%} of days", GOOD, (23, 48, 31)
    if cheaper >= 0.33:
        return f"AVERAGE PRICE · cheaper than {cheaper:.0%} of days", GOLD, (52, 43, 23)
    return f"EXPENSIVE · pricier than {1 - cheaper:.0%} of days", BAD, (51, 25, 26)


def _change_chip(d, x, y, label, v):
    if v is None:
        return _chip(d, x, y, f"{label}  n/a", fill=CELL, color=MUTED)
    col = GOOD if v < 0 else BAD if v > 0 else MUTED
    arrow = "▼" if v < 0 else "▲" if v > 0 else "•"
    return _chip(d, x, y, f"{label} {arrow} {abs(v) * 100:.1f}%", fill=CELL, color=col)


def _sparkline(d, box, values, color=GOLD):
    L, T, R, B = box
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = [(L + i * (R - L) / max(1, len(values) - 1), B - (v - lo) / span * (B - T)) for i, v in enumerate(values)]
    d.polygon(pts + [(R, B), (L, B)], fill=(52, 43, 23))
    d.line(pts, fill=color, width=3, joint="curve")
    x, y = pts[-1]
    d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color, outline=BG, width=2)


def _tile(d, box, label, value, sub=None, color=TEXT):
    _rr(d, box, fill=PANEL, r=14)
    d.text((box[0] + 18, box[1] + 24), label, font=F["s"], fill=MUTED, anchor="lm")
    d.text((box[0] + 18, box[1] + 58), value, font=F["h"], fill=color, anchor="lm")
    if sub:
        d.text((box[0] + 18, box[1] + 86), sub, font=F["s"], fill=DIM, anchor="lm")


def gold_card(market, gold_icon=None):
    st, pts = market["stats"], market["points"]
    cur = st["current"]
    prev = pts[-2]["price"] if len(pts) > 1 else None
    avg30 = sum(p["price"] for p in pts[-30:]) / len(pts[-30:])
    W, H, pad = 1000, 430, 32
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 5), fill=GOLD)

    if gold_icon:
        _paste_center(img, _fit(gold_icon, 92, 92), pad + 46, 84)
    x0 = pad + 112 if gold_icon else pad
    d.text((x0, 44), "GOLD BAR EXCHANGE", font=F["s"], fill=MUTED, anchor="lm")
    d.text((x0 - 2, 90), f"${cur:,}", font=F["title"], fill=TEXT, anchor="lm")
    d.text((x0, 132), "cash per gold bar", font=F["m"], fill=DIM, anchor="lm")

    x = 560
    x = _change_chip(d, x, 36, "1D", (cur - prev) / prev if prev else None)
    x = _change_chip(d, x, 36, "7D", st["changes"].get("7d"))
    _change_chip(d, x, 36, "30D", st["changes"].get("30d"))
    sig, col, bg = _signal(market)
    _chip(d, 560, 76, sig, fill=bg, color=col)
    # 14-day sparkline under the chips
    _sparkline(d, (566, 118, W - pad - 6, 160), [p["price"] for p in pts[-14:]])
    d.text((W - pad, 170), "last 14 days", font=F["s"], fill=DIM, anchor="rm")

    # tiles
    tw = (W - 2 * pad - 3 * 16) / 4
    y = 196
    vs = (cur - avg30) / avg30
    tiles = [
        ("VS 30-DAY AVG", f"{vs * 100:+.0f}%", f"avg {_money(avg30)}", GOOD if vs < 0 else BAD),
        ("ALL-TIME LOW", _money(st["min"]), "cheapest day so far", TEXT),
        ("ALL-TIME HIGH", _money(st["max"]), "priciest day so far", TEXT),
        ("30-BAR SKIN", _money(30 * cur), "Black & Gold AK74 today", GOLD),
    ]
    for i, (lab, val, sub, c) in enumerate(tiles):
        bx = pad + i * (tw + 16)
        _tile(d, (bx, y, bx + tw, y + 108), lab, val, sub, c)

    # skin price strip
    y2 = y + 128
    _rr(d, (pad, y2, W - pad, y2 + 52), fill=PANEL, r=14)
    d.text((pad + 18, y2 + 26), "SKIN PRICES TODAY", font=F["s"], fill=MUTED, anchor="lm")
    x = pad + 180
    for bars in (5, 10, 15, 30):
        x = _chip(d, x, y2 + 12, f"{bars} bars = {_money(bars * cur)}", fill=CELL, color=TEXT)

    d.text((pad, H - 22), "Lower = cheaper bars  ·  /chart for the full history", font=F["s"], fill=DIM, anchor="lm")
    d.text((W - pad, H - 22), "data: metaforge.app", font=F["s"], fill=DIM, anchor="rm")
    return _png(img)


def cost_card(market, bars, skins=None, gold_icon=None):
    st = market["stats"]
    cur = st["current"]
    avg30 = sum(p["price"] for p in market["points"][-30:]) / len(market["points"][-30:])
    skins = [s for s in (skins or []) if s.get("source") == "gold-market" and s.get("price")]
    affordable = sorted([s for s in skins if s["price"] <= bars], key=lambda s: (-s["price"], s.get("name", "")))

    W, pad = 1000, 32
    H = 446 if skins else 330
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 5), fill=GOLD)

    if gold_icon:
        _paste_center(img, _fit(gold_icon, 92, 92), pad + 46, 84)
    x0 = pad + 112 if gold_icon else pad
    d.text((x0, 44), f"{bars:,} GOLD BAR{'S' if bars != 1 else ''} COST", font=F["s"], fill=MUTED, anchor="lm")
    d.text((x0 - 2, 90), _money(bars * cur), font=F["title"], fill=GOLD, anchor="lm")
    d.text((x0, 132), f"${bars * cur:,} cash at today's ${cur:,}/bar", font=F["m"], fill=DIM, anchor="lm")
    sig, col, bg = _signal(market)
    tw = d.textlength(sig, font=F["s"])
    _chip(d, W - pad - tw - 20, 36, sig, fill=bg, color=col)

    tw = (W - 2 * pad - 2 * 16) / 3
    y = 170
    for i, (lab, rate, c) in enumerate((("AT ALL-TIME LOW", st["min"], GOOD), ("AT 30-DAY AVERAGE", avg30, TEXT),
                                        ("AT ALL-TIME HIGH", st["max"], BAD))):
        bx = pad + i * (tw + 16)
        diff = bars * rate - bars * cur
        _tile(d, (bx, y, bx + tw, y + 108), lab, _money(bars * rate),
              f"{'+' if diff >= 0 else '−'}{_money(abs(diff))} vs today", c)

    if skins:
        y2 = y + 128
        _rr(d, (pad, y2, W - pad, y2 + 90), fill=PANEL, r=14)
        d.text((pad + 18, y2 + 24), f"{len(affordable)} OF {len(skins)} GOLD MARKET ITEMS COST {bars} BARS OR LESS  ·  priciest first",
               font=F["s"], fill=MUTED, anchor="lm")
        x = pad + 18
        if not affordable:
            cheapest = min(s["price"] for s in skins)
            d.text((x, y2 + 58), f"Not enough for any item yet, the cheapest costs {cheapest} bars", font=F["b"], fill=MUTED, anchor="lm")
        for s in affordable[:4]:
            name = f"{(s.get('target') or {}).get('name', '')} {s['name']}".strip() if isinstance(s.get("target"), dict) else s["name"]
            label = f"{name} · {s['price']}"
            if x + d.textlength(label, font=F["s"]) + 30 > W - pad:
                break
            x = _chip(d, x, y2 + 44, label, fill=CELL, color=GOLD if s["price"] == bars else TEXT)

    d.text((pad, H - 22), "Converting cash to bars is final  ·  /chart to time it", font=F["s"], fill=DIM, anchor="lm")
    d.text((W - pad, H - 22), "data: metaforge.app", font=F["s"], fill=DIM, anchor="rm")
    return _png(img)


HELP = [
    ("/gold", "/gold", "Today's gold bar rate, changes and a buy signal"),
    ("/cost", "/cost bars:30", "Cash cost of gold bars, and which skins they cover"),
    ("/chart", "/chart period:30d", "Gold price history  ·  7D / 30D / 90D / ALL buttons"),
    ("/compare", "/compare m4 ak74 deagle", "Up to 3 weapons, shots to kill vs every armor tier"),
    ("/ammo", "/ammo mosin nagant", "FMJ vs HP vs AP (or slug vs buckshot) for one weapon"),
    ("/weapon", "/weapon m4", "Spray pattern + best attachments for recoil"),
]


def help_card(gold_icon=None):
    W, pad, row_h = 1000, 32, 74
    H = 150 + row_h * len(HELP) + 90
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 5), fill=GOLD)
    if gold_icon:
        _paste_center(img, _fit(gold_icon, 72, 72), pad + 36, 76)
    x0 = pad + 92 if gold_icon else pad
    d.text((x0, 58), "WARDOGS BOT", font=F["title"], fill=TEXT, anchor="lm")
    d.text((x0 + 2, 104), "Gold prices, weapon stats and ammo math, straight from MetaForge", font=F["m"], fill=MUTED, anchor="lm")
    y = 150
    for i, (cmd, example, desc) in enumerate(HELP):
        _rr(d, (pad, y, W - pad, y + row_h - 10), fill=PANEL, r=12)
        d.text((pad + 20, y + (row_h - 10) / 2), cmd, font=F["h"], fill=GOLD, anchor="lm")
        d.text((pad + 170, y + 22), desc, font=F["b"], fill=TEXT, anchor="lm")
        d.text((pad + 170, y + 46), example, font=F["m"], fill=DIM, anchor="lm")
        y += row_h
    tips = "Cards have buttons: hit zone, ammo type and distance redraw in place  ·  weapon names autocomplete"
    d.text((pad, H - 56), tips, font=F["s"], fill=MUTED, anchor="lm")
    d.line((pad, H - 40, W - pad, H - 40), fill=LINE, width=1)
    d.text((pad, H - 20), "Numbers match metaforge.app/wardogs/ballistics", font=F["s"], fill=DIM, anchor="lm")
    d.text((W - pad, H - 20), "data: metaforge.app", font=F["s"], fill=DIM, anchor="rm")
    return _png(img)
