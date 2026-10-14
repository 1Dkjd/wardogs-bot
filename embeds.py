"""Builds Discord embeds. Kept free of network calls so it can be tested offline."""
from datetime import datetime, timezone

import discord

from wardogs import ROUND_SHORT, SITE, money

GOLD = 0xF0B232
GREEN = 0x57F287
RED = 0xED4245


def _pct(v):
    if v is None:
        return "n/a"
    arrow = "🔻" if v < 0 else "🔺" if v > 0 else "➖"
    return f"{arrow} {v * 100:+.1f}%"


def gold_embed(market):
    pts = market["points"]
    st = market["stats"]
    cur = st["current"]
    prev = pts[-2]["price"] if len(pts) > 1 else None
    day = (cur - prev) / prev if prev else None
    avg30 = sum(p["price"] for p in pts[-30:]) / len(pts[-30:])
    color = GREEN if (day or 0) < 0 else RED if (day or 0) > 0 else GOLD

    e = discord.Embed(
        title="🪙 Gold Bar Exchange",
        url=f"{SITE}/market",
        description=f"## ${cur:,}\ncash per gold bar",
        color=color,
        timestamp=datetime.fromtimestamp(market["updatedAt"] / 1000, tz=timezone.utc),
    )
    e.add_field(name="vs yesterday", value=_pct(day))
    e.add_field(name="7 days", value=_pct(st["changes"].get("7d")))
    e.add_field(name="30 days", value=_pct(st["changes"].get("30d")))
    e.add_field(name="vs 30-day avg", value=_pct((cur - avg30) / avg30))
    e.add_field(name="All-time low", value=money(st["min"]))
    e.add_field(name="All-time high", value=money(st["max"]))
    e.set_footer(text="Lower = cheaper bars • MetaForge")
    return e


def cost_embed(market, bars):
    rate = market["stats"]["current"]
    lo, hi = market["stats"]["min"], market["stats"]["max"]
    e = discord.Embed(
        title=f"🪙 {bars:,} gold bar{'s' if bars != 1 else ''}",
        url=f"{SITE}/market",
        description=f"## {money(bars * rate)}\n`${bars * rate:,}` at today's rate of `${rate:,}`/bar",
        color=GOLD,
    )
    e.add_field(name="At all-time low", value=money(bars * lo))
    e.add_field(name="At all-time high", value=money(bars * hi))
    e.set_footer(text="MetaForge • rate changes daily")
    return e


def _table(rows):
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    lines = []
    for r in rows:
        cells = [str(c).ljust(widths[0]) if i == 0 else str(c).rjust(widths[i]) for i, c in enumerate(r)]
        lines.append("  ".join(cells))
    return "```\n" + "\n".join(lines) + "\n```"


def _armor_rows(b, zone):
    """[(label, armor_or_None)] for the zone: No armor, then each tier covering it."""
    rows = [("None", None)]
    for a in b.armour_for_zone(zone):
        kind = "Helm" if a["slot"] == "helmet" else "Armor"
        rows.append((f"L{a['name'].split()[1]} {kind}", a))
    return rows


def compare_embed(b, weapons, rnd, zone, rng):
    names = [w["name"] for w in weapons]
    rows = [[""] + names]

    def stat(label, fn):
        rows.append([label] + [fn(w) for w in weapons])

    stat("Calibre", lambda w: b.calibre(w).get("label", w.get("calibre", "?")))
    stat("Damage", lambda w: b.calibre(w).get("baseDamage", "-"))
    stat("RPM", lambda w: w.get("roundsPerMinute", "-"))
    stat("Velocity", lambda w: f"{w.get('muzzleVelocity', '-')}m/s")
    stat("Eff range", lambda w: f"{w.get('effectiveRange', '-')}m")
    stat("Mag", lambda w: w.get("magSize", "-"))
    stat("Accuracy", lambda w: f"{w['accuracyMoa']}MOA" if w.get("accuracyMoa") else "-")

    stk = [["Shots/TTK"] + names]
    for label, armor in _armor_rows(b, zone):
        row = [label]
        for w in weapons:
            h = b.hit(w, rnd, zone, armor, rng)
            mark = "*" if h and h["breaks"] else ""
            row.append(f"{h['shots']}{mark} {h['ttk']:.2f}s" if h and h["ttk"] is not None else "-")
        stk.append(row)

    e = discord.Embed(
        title=" vs ".join(names),
        url=f"{SITE}/ballistics?w={','.join(w['slug'] for w in weapons)}",
        color=GOLD,
    )
    e.add_field(name="Stats", value=_table(rows), inline=False)
    e.add_field(
        name=f"Shots to kill · {b.zones[zone]} · {ROUND_SHORT.get(rnd, rnd)} · {rng}m",
        value=_table(stk),
        inline=False,
    )
    e.set_footer(text=f"{b.health} HP • * plate breaks before the kill • TTK includes bullet travel • MetaForge")
    return e


def ammo_embed(b, w, zone, rng):
    cal = b.calibre(w)
    rounds = b.rounds_for(w)
    shorts = [ROUND_SHORT.get(r, r) for r in rounds]

    tbl = [["dmg (shots)"] + shorts]
    for label, armor in _armor_rows(b, zone):
        row = [label]
        for r in rounds:
            h = b.hit(w, r, zone, armor, rng)
            row.append(f"{h['dmg']:.0f} ({h['shots']}{'*' if h['breaks'] else ''})" if h else "-")
        tbl.append(row)

    mods = [["Modifier"] + shorts]
    mods.append(["vs flesh"] + [f"{b.combat(cal, r)['bare']:.0%}" for r in rounds])
    covering = b.armour_for_zone(zone)
    tier = covering[0]["tier"] if covering else "Armor.Medium"
    mods.append(["vs armor"] + [f"{b.combat(cal, r)['vsTier'].get(tier, 1):.0%}" for r in rounds])
    mods.append(["armor pen"] + [f"x{b.combat(cal, r)['penScalar']}" for r in rounds])
    mods.append(["plate dmg"] + [f"{b.plate_vs_fmj(cal, r):+.0%}" for r in rounds])

    e = discord.Embed(
        title=f"{w['name']} ammo · {cal.get('label', '')}",
        url=f"{SITE}/ballistics?w={w['slug']}",
        description=f"Base damage **{cal.get('baseDamage', '?')}** · {b.zones[zone]} · {rng}m",
        color=GOLD,
    )
    e.add_field(name="Damage per hit (shots to kill)", value=_table(tbl), inline=False)
    e.add_field(name="Round modifiers", value=_table(mods), inline=False)
    e.add_field(
        name="How to read it",
        value="**armor pen** scales the armor's reduction: x0.6 means armor blocks 40% less, x1.5 means it blocks 50% more. "
              "**plate dmg** is how fast the round wears down plates compared with FMJ.",
        inline=False,
    )
    e.set_footer(text=f"{b.health} HP • * plate breaks before the kill • MetaForge")
    return e
