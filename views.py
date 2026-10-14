"""Image-card rendering + interactive controls for /compare and /ammo."""
import asyncio
import io
import logging

import discord
from PIL import Image

import cards
from wardogs import ROUND_SHORT, SITE

log = logging.getLogger("wardogs-bot.views")

ZONES = [
    ("Head", "head"), ("Neck", "neck"), ("Upper torso", "torso_upper"), ("Middle torso", "torso_middle"),
    ("Lower torso", "torso_lower"), ("Pelvis", "pelvis"), ("Arm", "arm_upper"), ("Leg", "leg_thigh"),
]
ROUNDS = ["FMJ", "HollowPoint", "ArmorPiercing"]
DISTANCES = [10, 50, 100, 300]


def _img(data):
    if not data:
        return None
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        return None


async def render(mf, kind, slugs, rnd, zone, rng):
    """Build the PNG for a card. kind = 'ammo' | 'compare'."""
    b = await mf.ballistics()
    names = await mf.icon_names()
    weapons = [b.weapons[s] for s in slugs]
    weapon_icons = dict(zip(slugs, await asyncio.gather(*(mf.icon(names.get(s)) for s in slugs))))

    if kind == "weapon":
        w = weapons[0]
        A = await mf.attachments()
        picks = [r["pick"] for r in A.best_recoil_build(w)["slots"] if r["pick"]]
        datas = await asyncio.gather(*(mf.icon(p["icon"]) for p in picks))
        att_imgs = {p["slug"]: _img(d) for p, d in zip(picks, datas)}
        png = await asyncio.to_thread(cards.weapon_card, b, A, w, _img(weapon_icons[w["slug"]]), att_imgs)
    elif kind == "ammo":
        w = weapons[0]
        opts = b.ammo_options(w)
        datas = await asyncio.gather(*(mf.icon(o["icon"]) for o in opts))
        round_imgs = {o["short"]: _img(d) for o, d in zip(opts, datas)}
        png = await asyncio.to_thread(cards.ammo_card, b, w, zone, rng, _img(weapon_icons[w["slug"]]), round_imgs)
    else:
        imgs = {s: _img(d) for s, d in weapon_icons.items()}
        png = await asyncio.to_thread(cards.compare_card, b, weapons, rnd, zone, rng, imgs)
    return discord.File(png, f"wardogs-{kind}.png")


class ZoneSelect(discord.ui.Select):
    def __init__(self, current):
        super().__init__(
            placeholder="Hit zone",
            options=[discord.SelectOption(label=f"Hit zone: {n}", value=v, default=v == current) for n, v in ZONES],
            row=0,
        )

    async def callback(self, inter: discord.Interaction):
        self.view.zone = self.values[0]
        await self.view.refresh(inter)


class RoundButton(discord.ui.Button):
    def __init__(self, rnd, current):
        super().__init__(
            label=ROUND_SHORT[rnd],
            style=discord.ButtonStyle.primary if rnd == current else discord.ButtonStyle.secondary,
            row=1,
        )
        self.rnd = rnd

    async def callback(self, inter: discord.Interaction):
        self.view.rnd = self.rnd
        await self.view.refresh(inter)


class DistanceButton(discord.ui.Button):
    def __init__(self, metres, current):
        super().__init__(label=f"{metres} m", row=2,
                         style=discord.ButtonStyle.primary if metres == current else discord.ButtonStyle.secondary)
        self.metres = metres

    async def callback(self, inter: discord.Interaction):
        self.view.rng = self.metres
        await self.view.refresh(inter)


class CardView(discord.ui.View):
    def __init__(self, mf, kind, slugs, rnd="FMJ", zone="torso_upper", rng=50):
        super().__init__(timeout=900)
        self.mf, self.kind, self.slugs = mf, kind, slugs
        self.rnd, self.zone, self.rng = rnd, zone, rng
        self.message = None
        self._build()

    def _build(self):
        self.clear_items()
        if self.kind == "weapon":
            url = f"{SITE}/database/weapons/{self.slugs[0]}"
            self.add_item(discord.ui.Button(label="View on MetaForge", url=url, row=0))
            return
        self.add_item(ZoneSelect(self.zone))
        if self.kind == "compare":
            for r in ROUNDS:
                self.add_item(RoundButton(r, self.rnd))
        for m in DISTANCES:
            self.add_item(DistanceButton(m, self.rng))
        url = f"{SITE}/ballistics?w={','.join(self.slugs)}&round={ROUND_SHORT[self.rnd]}&range={self.rng}"
        self.add_item(discord.ui.Button(label="MetaForge", url=url, row=2))

    async def refresh(self, inter: discord.Interaction):
        await inter.response.defer()
        try:
            file = await render(self.mf, self.kind, self.slugs, self.rnd, self.zone, self.rng)
        except Exception:
            log.exception("Re-render failed")
            return await inter.followup.send("⚠️ Couldn't redraw that right now, try again in a minute.", ephemeral=True)
        self._build()
        await inter.edit_original_response(attachments=[file], view=self)

    async def on_timeout(self):
        # After 15 minutes the controls stop working, so grey them out (the MetaForge link keeps working).
        for item in self.children:
            if not (isinstance(item, discord.ui.Button) and item.url):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---------------- gold chart ----------------
CHART_RANGES = [("7D", "7d"), ("30D", "30d"), ("90D", "90d"), ("ALL", "all")]


async def render_chart(mf, rng):
    import chart  # local import: matplotlib is heavy and only needed here

    market = await mf.market()
    gold = _img(await mf.asset("ui/currency/gold"))
    png = await asyncio.to_thread(chart.render, market, rng, gold)
    return discord.File(png, "wardogs-gold.png")


class RangeButton(discord.ui.Button):
    def __init__(self, label, rng, current):
        super().__init__(label=label, row=0,
                         style=discord.ButtonStyle.primary if rng == current else discord.ButtonStyle.secondary)
        self.rng = rng

    async def callback(self, inter: discord.Interaction):
        view = self.view  # build() replaces the buttons (incl. this one), which clears self.view
        view.rng = self.rng
        await inter.response.defer()
        try:
            file = await render_chart(view.mf, self.rng)
        except Exception:
            log.exception("Chart re-render failed")
            return await inter.followup.send("⚠️ Couldn't redraw the chart right now.", ephemeral=True)
        view.build()
        await inter.edit_original_response(attachments=[file], view=view)


class ChartView(discord.ui.View):
    def __init__(self, mf, rng="30d"):
        super().__init__(timeout=900)
        self.mf, self.rng, self.message = mf, rng, None
        self.build()

    def build(self):
        self.clear_items()
        for label, rng in CHART_RANGES:
            self.add_item(RangeButton(label, rng, self.rng))
        self.add_item(discord.ui.Button(label="View on MetaForge", url=f"{SITE}/market", row=0))

    on_timeout = CardView.on_timeout


# ---------------- gold / cost cards ----------------
async def render_gold(mf):
    market = await mf.market()
    gold = _img(await mf.asset("ui/currency/gold"))
    png = await asyncio.to_thread(cards.gold_card, market, gold)
    return discord.File(png, "wardogs-gold.png")


async def render_cost(mf, bars):
    market = await mf.market()
    try:
        skins = (await mf.skins()).get("skins", [])
    except Exception:
        skins = []
    gold = _img(await mf.asset("ui/currency/gold"))
    png = await asyncio.to_thread(cards.cost_card, market, bars, skins, gold)
    return discord.File(png, "wardogs-cost.png")


def market_link_view():
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="Gold Bar Market on MetaForge", url=f"{SITE}/market"))
    return v


async def render_help(mf):
    gold = _img(await mf.asset("ui/currency/gold"))
    return discord.File(await asyncio.to_thread(cards.help_card, gold), "wardogs-help.png")


# ---------------- vehicles ----------------
async def render_vehicle(mf, slug, mode="kill"):
    from wardogs import classify_sources

    vehicles = await mf.vehicles()
    v = vehicles[slug]
    b = await mf.ballistics()
    db = await mf._get("database", mf.ttl_static)
    items = {i["slug"]: i for i in db.get("items", []) if not i.get("wip")}
    page = await mf.vehicle_page(slug)
    sources = classify_sources(page["rounds"], b, items)
    names = {v.get("icon")} | {s.get("icon") for s in sources if s.get("icon") and s["kind"] != "vehicle"}
    names.discard(None)
    datas = await asyncio.gather(*(mf.icon(n) for n in names))
    icons = {n: _img(d) for n, d in zip(names, datas)}
    if mode == "zones":
        png = await asyncio.to_thread(cards.vehicle_zones_card, v, page["zones"], sources, icons)
    else:
        png = await asyncio.to_thread(cards.vehicle_card, v, sources, icons)
    return discord.File(png, f"wardogs-vehicle-{mode}.png")


class VehicleModeButton(discord.ui.Button):
    def __init__(self, label, mode, current):
        super().__init__(label=label, row=0,
                         style=discord.ButtonStyle.primary if mode == current else discord.ButtonStyle.secondary)
        self.mode = mode

    async def callback(self, inter: discord.Interaction):
        view = self.view  # build() replaces the buttons, which clears self.view
        view.mode = self.mode
        await inter.response.defer()
        try:
            file = await render_vehicle(view.mf, view.slug, self.mode)
        except Exception:
            log.exception("Vehicle re-render failed")
            return await inter.followup.send("⚠️ Couldn't redraw that right now.", ephemeral=True)
        view.build()
        await inter.edit_original_response(attachments=[file], view=view)


class VehicleView(discord.ui.View):
    def __init__(self, mf, slug, mode="kill"):
        super().__init__(timeout=900)
        self.mf, self.slug, self.mode, self.message = mf, slug, mode, None
        self.build()

    def build(self):
        self.clear_items()
        self.add_item(VehicleModeButton("What kills it", "kill", self.mode))
        self.add_item(VehicleModeButton("Where to shoot", "zones", self.mode))
        self.add_item(discord.ui.Button(label="View on MetaForge", url=f"{SITE}/database/vehicles/{self.slug}", row=0))

    on_timeout = CardView.on_timeout
