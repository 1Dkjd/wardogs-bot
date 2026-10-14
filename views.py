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

    if kind == "ammo":
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


class CardView(discord.ui.View):
    def __init__(self, mf, kind, slugs, rnd="FMJ", zone="torso_upper", rng=50):
        super().__init__(timeout=900)
        self.mf, self.kind, self.slugs = mf, kind, slugs
        self.rnd, self.zone, self.rng = rnd, zone, rng
        self.message = None
        self._build()

    def _build(self):
        self.clear_items()
        self.add_item(ZoneSelect(self.zone))
        if self.kind == "compare":
            for r in ROUNDS:
                self.add_item(RoundButton(r, self.rnd))
        url = f"{SITE}/ballistics?w={','.join(self.slugs)}&round={ROUND_SHORT[self.rnd]}&range={self.rng}"
        self.add_item(discord.ui.Button(label="View on MetaForge", url=url, row=1))

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
        self.view.rng = self.rng
        await inter.response.defer()
        try:
            file = await render_chart(self.view.mf, self.rng)
        except Exception:
            log.exception("Chart re-render failed")
            return await inter.followup.send("⚠️ Couldn't redraw the chart right now.", ephemeral=True)
        self.view.build()
        await inter.edit_original_response(attachments=[file], view=self.view)


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
