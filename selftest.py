"""Daily self-test (render every command against live MetaForge data) and owner error DMs."""
import asyncio
import logging
import os
import time
import traceback

import discord

import views

log = logging.getLogger("wardogs-bot.selftest")

ENDPOINTS = ["market", "ballistics/v2", "database", "attachment-stats", "skins", "vehicles"]


async def run(mf):
    """Returns [(check, ok, detail, seconds)]. Fetches MetaForge fresh so site changes are caught."""
    results = []

    async def check(name, coro):
        t = time.time()
        try:
            await coro
            results.append((name, True, "", time.time() - t))
        except Exception as e:  # noqa: BLE001 - we want every failure reported
            results.append((name, False, f"{type(e).__name__}: {e}"[:300], time.time() - t))

    for ep in ENDPOINTS:
        await check(f"api/{ep}", mf._get(ep, 0))
    mf._cache.pop("page:vehicle:humvee", None)
    await check("page/vehicle", mf.vehicle_page("humvee"))
    await check("/gold", views.render_gold(mf))
    await check("/cost", views.render_cost(mf, 10))
    await check("/chart", views.render_chart(mf, "30d"))
    await check("/compare", views.render(mf, "compare", ["m4", "ak74"], "FMJ", "torso_upper", 50))
    await check("/ammo", views.render(mf, "ammo", ["m4"], "FMJ", "torso_upper", 50))
    await check("/weapon", views.render(mf, "weapon", ["m4"], "FMJ", "torso_upper", 50))
    await check("/vehicle", views.render_vehicle(mf, "humvee", "kill"))
    await check("/vehicle zones", views.render_vehicle(mf, "humvee", "zones"))
    await check("/help", views.render_help(mf))
    return results


def summary(results):
    bad = [r for r in results if not r[1]]
    lines = [f"{'✅' if ok else '❌'} `{name}` {f'{secs:.1f}s' if ok else detail}" for name, ok, detail, secs in results]
    head = (f"**WARDOGS bot self-test: {len(bad)} of {len(results)} checks failed**" if bad
            else f"**WARDOGS bot self-test: all {len(results)} checks passed**")
    return head + "\n" + "\n".join(lines)


class OwnerAlerts:
    """DMs the bot owner when something breaks. Same error is sent at most once per COOLDOWN seconds."""

    COOLDOWN = 30 * 60

    def __init__(self, client):
        self.client = client
        self._owner = None
        self._last = {}
        self._suppressed = {}

    async def owner(self):
        if self._owner:
            return self._owner
        oid = os.environ.get("OWNER_ID")
        if oid:
            self._owner = await self.client.fetch_user(int(oid))
        else:
            app = await self.client.application_info()
            self._owner = app.team.owner if app.team and app.team.owner else app.owner
        return self._owner

    async def send(self, text):
        try:
            user = await self.owner()
            for i in range(0, len(text), 1900):  # Discord message limit is 2000 chars
                await user.send(text[i:i + 1900])
        except Exception:
            log.exception("Couldn't DM the owner")

    async def error(self, where, err, context=""):
        sig = f"{where}|{type(err).__name__}|{str(err)[:80]}"
        now = time.time()
        if now - self._last.get(sig, 0) < self.COOLDOWN:
            self._suppressed[sig] = self._suppressed.get(sig, 0) + 1
            return
        repeats = self._suppressed.pop(sig, 0)
        self._last[sig] = now
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))[-1400:]
        msg = (f"⚠️ **{where}** failed{f' ({context})' if context else ''}"
               f"{f' · happened {repeats} more times in the last 30 min' if repeats else ''}\n```py\n{tb}\n```")
        await self.send(msg)
