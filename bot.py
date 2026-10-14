"""WARDOGS Discord bot: gold, compare, ammo, weapon, vehicle and patch-change cards, plus daily/patch posts."""
import asyncio
import json
import logging
import os
import time

import discord
from discord import app_commands
from discord.ext import tasks

import cards
import patches
import selftest
import views
from wardogs import RANGES, MetaForge

TOKEN = os.environ["DISCORD_TOKEN"]
# Optional: your home server. Old server-only command copies there get cleaned up so they don't show twice.
GUILD_ID = os.environ.get("GUILD_ID")
# Optional: channel for the automatic daily gold post (your server).
DAILY_CHANNEL_ID = os.environ.get("DAILY_CHANNEL_ID")
# Optional: channel for balance-patch alerts. Falls back to the daily channel.
PATCH_CHANNEL_ID = os.environ.get("PATCH_CHANNEL_ID") or DAILY_CHANNEL_ID
STATE_FILE = os.environ.get("STATE_FILE", "/data/state.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("wardogs-bot")

mf = MetaForge()
client = discord.Client(intents=discord.Intents.default())
# Commands work in any server the bot is in, and for people who add it to their own account
# (user install), including DMs and group chats.
alerts = selftest.OwnerAlerts(client)  # DMs the bot owner when something breaks
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


async def vehicle_autocomplete(_: discord.Interaction, current: str):
    vs = await mf.vehicles()
    q = (current or "").lower()
    hits = sorted((v for v in vs.values() if q in v["name"].lower() or q in v["slug"]), key=lambda v: v["name"])
    return [app_commands.Choice(name=v["name"], value=v["slug"]) for v in hits[:25]]


@tree.command(description="What kills a vehicle, and how many hits it takes")
@app_commands.describe(vehicle="Vehicle")
@app_commands.autocomplete(vehicle=vehicle_autocomplete)
async def vehicle(inter: discord.Interaction, vehicle: str):
    await inter.response.defer()
    vs = await mf.vehicles()
    slug = vehicle if vehicle in vs else next((k for k, v in vs.items() if v["name"].lower() == vehicle.lower()), None)
    if not slug:
        return await error(inter, f"Couldn't find a vehicle called **{vehicle}**.")
    view = views.VehicleView(mf, slug)
    view.message = await inter.followup.send(file=await views.render_vehicle(mf, slug), view=view, wait=True)


@tree.command(name="help", description="What this bot can do")
async def help_cmd(inter: discord.Interaction):
    await inter.response.defer()
    await inter.followup.send(file=await views.render_help(mf))


@tree.error
async def on_tree_error(inter: discord.Interaction, err: app_commands.AppCommandError):
    log.exception("Command failed", exc_info=err)
    original = getattr(err, "original", err)
    cmd = f"/{inter.command.qualified_name}" if inter.command else "command"
    params = ", ".join(f"{k}={v}" for k, v in vars(inter.namespace).items())
    where = inter.guild.name if inter.guild else "DM / user install"
    asyncio.create_task(alerts.error(cmd, original, f"{params} · {where}" if params else where))
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
    except Exception as e:
        log.exception("Daily post: couldn't fetch market")
        await alerts.error("Daily gold post", e)
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
        await alerts.error("Daily gold post", e, f"channel {DAILY_CHANNEL_ID}")


# ---------------- balance patch alerts ----------------
watcher = patches.PatchWatcher(os.path.dirname(STATE_FILE) or "/data")


async def _channel(cid):
    cid = int(cid)
    return client.get_channel(cid) or await client.fetch_channel(cid)


@tasks.loop(hours=3)
async def patch_watch():
    try:
        b, db, st = await mf.patch_sources()
    except Exception as e:
        log.exception("Patch check: couldn't fetch MetaForge data")
        await alerts.error("Balance-patch check", e)
        return
    changes = watcher.check(patches.snapshot(b, db, st))
    if not changes:
        return
    log.info("Balance changes detected: %d", len(changes))
    if PATCH_CHANNEL_ID:
        try:
            png = await asyncio.to_thread(cards.patch_card, changes, time.time())
            await (await _channel(PATCH_CHANNEL_ID)).send(file=discord.File(png, "wardogs-patch.png"))
        except discord.HTTPException as e:
            log.warning("Patch alert post failed: %s", e)
            await alerts.error("Balance-patch alert post", e, f"channel {PATCH_CHANNEL_ID}")


@tree.command(description="The latest balance changes the bot spotted")
async def changes(inter: discord.Interaction):
    await inter.response.defer()
    last = watcher.last()
    if not last:
        return await inter.followup.send("No balance changes spotted yet. The bot checks MetaForge every 3 hours "
                                         "and posts here when weapon, ammo, armor or price stats change.")
    png = await asyncio.to_thread(cards.patch_card, last["changes"], last["detected"])
    await inter.followup.send(file=discord.File(png, "wardogs-patch.png"))


# ---------------- self-test ----------------
_selftest_state = {"failed": False}


async def _run_selftest(notify=True):
    results = await selftest.run(mf)
    failed = any(not ok for _, ok, _, _ in results)
    log.info(selftest.summary(results).splitlines()[0])
    if notify and failed:
        await alerts.send(selftest.summary(results))
    elif notify and _selftest_state["failed"] and not failed:
        await alerts.send("✅ **WARDOGS bot self-test passing again.** Everything works.")
    _selftest_state["failed"] = failed
    return results


@tasks.loop(hours=24)
async def daily_selftest():
    try:
        await _run_selftest()
    except Exception as e:
        log.exception("Self-test crashed")
        await alerts.error("Self-test", e)


@daily_selftest.before_loop
async def _before_selftest():
    await client.wait_until_ready()
    await asyncio.sleep(120)  # let startup settle first


@tree.command(name="selftest", description="(Bot owner) Test every command against MetaForge right now")
@app_commands.default_permissions(administrator=True)
async def selftest_cmd(inter: discord.Interaction):
    owner = await alerts.owner()
    if inter.user.id != owner.id:
        return await inter.response.send_message("Only the bot's owner can run this.", ephemeral=True)
    await inter.response.defer(ephemeral=True)
    results = await _run_selftest(notify=False)
    await inter.followup.send(selftest.summary(results)[:1990], ephemeral=True)


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
    if not patch_watch.is_running():
        patch_watch.start()
    if not daily_selftest.is_running():
        daily_selftest.start()


client.run(TOKEN, log_handler=None)
