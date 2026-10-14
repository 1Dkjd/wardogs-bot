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


def _header(img, d, b, w, icon, zone, rng, width, subtitle_extra=""):
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
    ctx = f"{b.zones[zone].upper()} · {rng} M"
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
