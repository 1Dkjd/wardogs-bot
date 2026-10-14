"""WARDOGS Discord bot: /gold /cost /chart /compare /ammo /weapon /help + optional daily gold post."""
import json
import logging
import os

import discord
from discord import app_commands
from discord.ext import tasks

import views
from wardogs import RANGES, MetaForge

TOKEN = os.environ["DISCORD_TOKEN"]
# Optional: your home server. Old server-only command copies there get cleaned up so they don't show twice.
GUILD_ID = os.environ.get("GUILD_ID")
# Optional: channel for the automatic daily gold post (your server).
DAILY_CHANNEL_ID = os.environ.get("DAILY_CHANNEL_ID")
STATE_FILE = os.environ.get("STATE_FILE", "/data/state.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("wardogs-bot")

mf = MetaForge()
client = discord.Client(intents=discord.Intents.default())
# Commands work in any server the bot is in, and for people who add it to their own account
# (user install), including DMs and group chats.
tree = app_commands.CommandTree(
    client,
    allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
    allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
)

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
    await inter.followup.send(file=await views.render_gold(mf), view=views.market_link_view())


@tree.command(description="What a number of gold bars costs in cash today")
@app_commands.describe(bars="How many gold bars")
async def cost(inter: discord.Interaction, bars: app_commands.Range[int, 1, 100000]):
    await inter.response.defer()
    await inter.followup.send(file=await views.render_cost(mf, bars), view=views.market_link_view())


@tree.command(name="chart", description="Gold bar price history from MetaForge")
@app_commands.describe(period="Time range (you can switch with the buttons too)")
@app_commands.choices(period=RANGE_CHOICES)
async def chart_cmd(inter: discord.Interaction, period: app_commands.Choice[str] = None):
    await inter.response.defer()
    rng = period.value if period else "30d"
    view = views.ChartView(mf, rng)
    file = await views.render_chart(mf, rng)
    view.message = await inter.followup.send(file=file, view=view, wait=True)


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


@tree.command(description="Spray pattern and the best attachments for recoil")
@app_commands.describe(weapon="Weapon")
@app_commands.autocomplete(weapon=weapon_autocomplete)
async def weapon(inter: discord.Interaction, weapon: str):
    await inter.response.defer()
    b = await mf.ballistics()
    w = b.find_weapon(weapon)
    if not w:
        return await error(inter, f"Couldn't find a weapon called **{weapon}**.")
    await send_card(inter, "weapon", [w["slug"]], "FMJ", "torso_upper", 50)


@tree.command(name="help", description="What this bot can do")
async def help_cmd(inter: discord.Interaction):
    await inter.response.defer()
    await inter.followup.send(file=await views.render_help(mf))


@tree.error
async def on_tree_error(inter: discord.Interaction, err: app_commands.AppCommandError):
    log.exception("Command failed", exc_info=err)
    await error(inter, "Couldn't reach MetaForge right now. Try again in a minute.")


# ---------------- state ----------------
def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# ---------------- daily post ----------------
@tasks.loop(minutes=30)
async def daily_post():
    try:
        market = await mf.market()
    except Exception:
        log.exception("Daily post: couldn't fetch market")
        return
    latest = market["points"][-1]["t"]
    state = _load(STATE_FILE)
    if state.get("last_point") == latest:
        return
    first_run = state.get("last_point") is None  # don't post on the very first start, so restarts don't spam
    _save(STATE_FILE, {"last_point": latest})
    if first_run:
        return
    try:
        cid = int(DAILY_CHANNEL_ID)
        channel = client.get_channel(cid) or await client.fetch_channel(cid)
        await channel.send(file=await views.render_gold(mf), view=views.market_link_view())
    except discord.HTTPException as e:
        log.warning("Daily post to channel %s failed: %s", DAILY_CHANNEL_ID, e)


@client.event
async def on_ready():
    synced = await tree.sync()  # global: every server + user installs (can take a few minutes the first time)
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.clear_commands(guild=guild)
        await tree.sync(guild=guild)  # removes the old server-only copies so commands don't appear twice
    log.info("Logged in as %s in %d servers, synced %d commands", client.user, len(client.guilds), len(synced))
    if DAILY_CHANNEL_ID and not daily_post.is_running():
        daily_post.start()


client.run(TOKEN, log_handler=None)
