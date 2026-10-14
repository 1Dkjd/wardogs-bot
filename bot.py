"""WARDOGS Discord bot: /gold /cost /chart /compare /ammo + optional daily gold post."""
import json
import logging
import os

import discord
from discord import app_commands
from discord.ext import tasks

import chart
import embeds
import views
from wardogs import RANGES, MetaForge, market_points

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = os.environ.get("GUILD_ID")  # set for instant command sync on your server
DAILY_CHANNEL_ID = os.environ.get("DAILY_CHANNEL_ID")  # optional: auto-post new rate here
STATE_FILE = os.environ.get("STATE_FILE", "/data/state.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("wardogs-bot")

mf = MetaForge()
client = discord.Client(intents=discord.Intents.default())
tree = app_commands.CommandTree(client)

ZONE_CHOICES = [app_commands.Choice(name=n, value=v) for n, v in views.ZONES]
ROUND_CHOICES = [app_commands.Choice(name=n, value=v) for n, v in
                 [("Standard (FMJ)", "FMJ"), ("Flesh Damage (HP)", "HollowPoint"), ("Armor Piercing (AP)", "ArmorPiercing")]]
RANGE_CHOICES = [app_commands.Choice(name=k, value=k) for k in RANGES]


async def weapon_autocomplete(_: discord.Interaction, current: str):
    b = await mf.ballistics()
    return [app_commands.Choice(name=w["name"], value=w["slug"]) for w in b.search_weapons(current)]


async def error(inter: discord.Interaction, msg: str):
    send = inter.followup.send if inter.response.is_done() else inter.response.send_message
    await send(f"⚠️ {msg}", ephemeral=True)


async def send_card(inter, kind, slugs, rnd, zone, rng):
    view = views.CardView(mf, kind, slugs, rnd, zone, rng)
    file = await views.render(mf, kind, slugs, rnd, zone, rng)
    view.message = await inter.followup.send(file=file, view=view, wait=True)


# ---------------- commands ----------------
@tree.command(description="Today's gold bar exchange rate")
async def gold(inter: discord.Interaction):
    await inter.response.defer()
    await inter.followup.send(embed=embeds.gold_embed(await mf.market()))


@tree.command(description="What a number of gold bars costs in cash today")
@app_commands.describe(bars="How many gold bars")
async def cost(inter: discord.Interaction, bars: app_commands.Range[int, 1, 100000]):
    await inter.response.defer()
    await inter.followup.send(embed=embeds.cost_embed(await mf.market(), bars))


@tree.command(name="chart", description="Gold bar price history from MetaForge")
@app_commands.describe(period="Time range")
@app_commands.choices(period=RANGE_CHOICES)
async def chart_cmd(inter: discord.Interaction, period: app_commands.Choice[str] = None):
    await inter.response.defer()
    rng = period.value if period else "30d"
    pts = market_points(await mf.market(), rng)
    if len(pts) < 2:
        return await error(inter, "Not enough price history for that range yet.")
    png = chart.render(pts, "all time" if rng == "all" else f"last {rng}")
    e = discord.Embed(title="🪙 Gold bar price history", url="https://metaforge.app/wardogs/market", color=embeds.GOLD)
    e.set_image(url="attachment://gold.png")
    e.set_footer(text=f"{len(pts)} days • MetaForge")
    await inter.followup.send(embed=e, file=discord.File(png, "gold.png"))


@tree.command(description="Compare weapons side by side, with shots to kill vs every armor tier")
@app_commands.describe(weapon1="First weapon", weapon2="Second weapon", weapon3="Optional third weapon",
                       round="Ammo type (default FMJ)", zone="Hit zone (default upper torso)",
                       distance="Distance in meters (default 50)")
@app_commands.choices(round=ROUND_CHOICES, zone=ZONE_CHOICES)
@app_commands.autocomplete(weapon1=weapon_autocomplete, weapon2=weapon_autocomplete, weapon3=weapon_autocomplete)
async def compare(inter: discord.Interaction, weapon1: str, weapon2: str, weapon3: str = None,
                  round: app_commands.Choice[str] = None, zone: app_commands.Choice[str] = None,
                  distance: app_commands.Range[int, 1, 1500] = 50):
    await inter.response.defer()
    b = await mf.ballistics()
    ws = []
    for q in filter(None, [weapon1, weapon2, weapon3]):
        w = b.find_weapon(q)
        if not w:
            return await error(inter, f"Couldn't find a weapon called **{q}**.")
        ws.append(w)
    await send_card(inter, "compare", [w["slug"] for w in ws], round.value if round else "FMJ",
                    zone.value if zone else "torso_upper", distance)


@tree.command(description="FMJ vs HP vs AP for a weapon: damage, shots to kill and armor penetration")
@app_commands.describe(weapon="Weapon (uses its calibre)", zone="Hit zone (default upper torso)",
                       distance="Distance in meters (default 50)")
@app_commands.choices(zone=ZONE_CHOICES)
@app_commands.autocomplete(weapon=weapon_autocomplete)
async def ammo(inter: discord.Interaction, weapon: str, zone: app_commands.Choice[str] = None,
               distance: app_commands.Range[int, 1, 1500] = 50):
    await inter.response.defer()
    b = await mf.ballistics()
    w = b.find_weapon(weapon)
    if not w:
        return await error(inter, f"Couldn't find a weapon called **{weapon}**.")
    if not b.calibre(w).get("baseDamage"):
        return await error(inter, f"MetaForge has no ammo damage data for **{w['name']}**.")
    await send_card(inter, "ammo", [w["slug"]], "FMJ", zone.value if zone else "torso_upper", distance)


@tree.error
async def on_tree_error(inter: discord.Interaction, err: app_commands.AppCommandError):
    log.exception("Command failed", exc_info=err)
    await error(inter, "Couldn't reach MetaForge right now. Try again in a minute.")


# ---------------- daily post ----------------
def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(s):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)


@tasks.loop(minutes=30)
async def daily_post():
    try:
        market = await mf.market()
        latest = market["points"][-1]["t"]
        state = _load_state()
        if state.get("last_point") == latest:
            return
        channel = client.get_channel(int(DAILY_CHANNEL_ID)) or await client.fetch_channel(int(DAILY_CHANNEL_ID))
        if state.get("last_point") is not None:  # skip the very first run so restarts don't spam
            await channel.send(embed=embeds.gold_embed(market))
        _save_state({"last_point": latest})
    except Exception:
        log.exception("Daily post failed")


@client.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
    else:
        synced = await tree.sync()
    log.info("Logged in as %s, synced %d commands", client.user, len(synced))
    if DAILY_CHANNEL_ID and not daily_post.is_running():
        daily_post.start()


client.run(TOKEN, log_handler=None)
