"""MetaForge WARDOGS data client + damage math.

Damage model (verified against metaforge.app/wardogs/ballistics):
  per_hit = baseDamage * zoneMult * falloff(range) * roundMult
  roundMult = combat[round].bare                              (zone not covered by armor)
            = combat[round].vsTier[tier] * (1 - reduction% * penScalar)   (zone covered)
  plate wear per hit = baseDamage * falloff * plateArmor (or plateHelmet);
  once the plate's durability hits 0, later shots deal the unarmored (bare) damage.
  shots   = hits until health <= 0
  ttk     = (shots - 1) * 60 / rpm + travel time (range / velocity, +1% for drag)
  buckshot multiplies damage and plate wear by the pellet count (all pellets hit)
"""
import math
import os
import re
import time

import aiohttp

API = "https://metaforge.app/api/wardogs"
SITE = "https://metaforge.app/wardogs"
STATIC = "https://static.metaforge.app/wardogs"
ICON_DIR = os.environ.get("ICON_DIR", "/data/icons")
UA = {"User-Agent": "Mozilla/5.0 (wardogs-discord-bot; personal use)"}

ROUND_SHORT = {"FMJ": "FMJ", "HollowPoint": "HP", "ArmorPiercing": "AP"}
DEFAULT_COMBAT = {"bare": 1, "penScalar": 1, "vsTier": {}, "plateArmor": 0.4, "plateHelmet": 0.4}
HIDDEN_WEAPONS = {"leapord-barrel-test"}


class MetaForge:
    def __init__(self, ttl_market=300, ttl_static=6 * 3600):
        self._cache = {}
        self.ttl_market = ttl_market
        self.ttl_static = ttl_static

    async def _get(self, path, ttl):
        hit = self._cache.get(path)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(f"{API}/{path}") as r:
                r.raise_for_status()
                data = await r.json(content_type=None)
        self._cache[path] = (time.time(), data)
        return data

    async def market(self):
        return await self._get("market", self.ttl_market)

    async def ballistics(self):
        return Ballistics(await self._get("ballistics", self.ttl_static))

    async def patch_sources(self):
        """Fresh (uncached) copies of everything the patch watcher snapshots. Also refreshes the command cache."""
        return (await self._get("ballistics", 0), await self._get("database", 0),
                await self._get("attachment-stats", 0))

    async def skins(self):
        return await self._get("skins", self.ttl_static)

    async def vehicles(self):
        db = await self._get("database", self.ttl_static)
        extra = (await self._get("vehicles", self.ttl_static)).get("vehicles", {})
        out = {}
        for i in db.get("items", []):
            if i.get("tab") == "vehicles" and not i.get("wip") and i.get("vehicle"):
                out[i["slug"]] = {**i, "protection": (extra.get(i["slug"]) or {}).get("protection", [])}
        return out

    async def destroy_list(self, slug):
        """MetaForge's 'what destroys it' ranking for a vehicle (server-rendered on its page), cached."""
        key = f"page:vehicle:{slug}"
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self.ttl_static:
            return hit[1]
        async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(f"{SITE}/database/vehicles/{slug}") as r:
                r.raise_for_status()
                rows = parse_destroy_list(await r.text())
        self._cache[key] = (time.time(), rows)
        return rows

    async def attachments(self):
        db = await self._get("database", self.ttl_static)
        stats = await self._get("attachment-stats", self.ttl_static)
        return Attachments(db, stats)

    async def icon_names(self):
        """slug -> icon name, from the item database (ballistics data has no icons)."""
        try:
            db = await self._get("database", self.ttl_static)
        except Exception:
            return {}  # icons are cosmetic; cards still render without them
        return {i["slug"]: i["icon"] for i in db.get("items", []) if i.get("icon")}

    async def icon(self, name):
        """Item icon (weapons, ammo) as raw bytes, cached on disk. None if unavailable."""
        return await self.asset(f"icons/{name}") if name else None

    async def asset(self, path):
        """Any MetaForge static image, e.g. 'ui/currency/gold'. Cached on disk."""
        cache = os.path.join(ICON_DIR, path.replace("/", "_") + ".webp")
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                return f.read()
        try:
            async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.get(f"{STATIC}/{path}.webp") as r:
                    if r.status != 200:
                        return None
                    data = await r.read()
            os.makedirs(ICON_DIR, exist_ok=True)
            with open(cache, "wb") as f:
                f.write(data)
            return data
        except Exception:
            return None


class Ballistics:
    def __init__(self, raw):
        self.raw = raw
        self.health = raw.get("assumedHealth", 100)
        self.weapons = {w["slug"]: w for w in raw["weapons"] if w["slug"] not in HIDDEN_WEAPONS}
        self.calibres = raw["calibres"]
        self.zones = {h["key"]: h["label"] for h in raw["hitLocations"]}
        self.armour = raw["armour"]

    # ---------- lookups ----------
    def find_weapon(self, q):
        q = (q or "").strip().lower()
        if q in self.weapons:
            return self.weapons[q]
        for w in self.weapons.values():
            if w["name"].lower() == q or w["slug"].replace("-", "") == q.replace("-", "").replace(" ", ""):
                return w
        return None

    def search_weapons(self, q, limit=25):
        q = (q or "").lower()
        out = [w for w in self.weapons.values() if q in w["name"].lower() or q in w["slug"]]
        return sorted(out, key=lambda w: w["name"])[:limit]

    def calibre(self, w):
        return self.calibres.get(w.get("calibre"), {})

    def combat(self, cal, rnd):
        return (cal.get("combat") or {}).get(rnd, DEFAULT_COMBAT)

    def rounds_for(self, w):
        cal = self.calibre(w)
        loads = cal.get("loads") or ["FMJ"]
        return [r for r in ("FMJ", "HollowPoint", "ArmorPiercing") if r in loads] or loads

    def effective_round(self, w, rnd, cal_key=None):
        """The round actually used: falls back to FMJ when the calibre has no such load (MetaForge does the same)."""
        cal = self.calibres.get(cal_key) if cal_key else self.calibre(w)
        loads = (cal or {}).get("loads") or ["FMJ"]
        return rnd if rnd in loads else ("FMJ" if "FMJ" in loads else loads[0])

    def ammo_options(self, w):
        """Columns for /ammo: FMJ/HP/AP of the weapon's calibre, or each shell type for shotguns."""
        shells = [k for k in (w.get("shells") or []) if self.calibres.get(k, {}).get("baseDamage")]
        if len(shells) > 1:
            out = []
            for k in shells:
                cal = self.calibres[k]
                rnd = self.effective_round(w, "FMJ", k)
                label = cal.get("label") or k
                short = "SLUG" if "slug" in (k + label).lower() else "BUCK" if "buck" in (k + label).lower() else label
                out.append({"cal": k, "rnd": rnd, "short": short, "name": label,
                            "icon": (cal.get("roundIcons") or {}).get(rnd)})
            return out
        cal = self.calibre(w)
        names = {"FMJ": "Standard", "HollowPoint": "Flesh Damage", "ArmorPiercing": "Armor Piercing"}
        return [{"cal": w.get("calibre"), "rnd": r, "short": ROUND_SHORT.get(r, r), "name": names.get(r, r),
                 "icon": (cal.get("roundIcons") or {}).get(r)} for r in self.rounds_for(w)]

    def armour_for_zone(self, zone):
        """Armor pieces that cover this zone, sorted by tier (L1..L4)."""
        return [a for a in self.armour if zone in a["covers"]]

    def zone_mult(self, w, zone):
        hb = self.raw["hitboxes"].get(w.get("weaponClass") or w.get("subcategory"), {})
        return hb.get(zone, 1.0)

    # ---------- math ----------
    @staticmethod
    def falloff(w, rng):
        pts = w.get("falloff") or []
        if not pts:
            return 1.0
        if rng <= pts[0][0]:
            return pts[0][1]
        for (d0, m0, *_), (d1, m1, *_) in zip(pts, pts[1:]):
            if d0 <= rng <= d1:
                return m0 + (m1 - m0) * (rng - d0) / (d1 - d0) if d1 > d0 else m1
        return pts[-1][1]

    def hit(self, w, rnd, zone, armor=None, rng=50, cal_key=None):
        cal = self.calibres.get(cal_key, {}) if cal_key else self.calibre(w)
        base = cal.get("baseDamage")
        if not base:
            return None
        rnd = self.effective_round(w, rnd, cal_key)
        c = self.combat(cal, rnd)
        pellets = cal.get("pellets") or 1  # buckshot: every pellet assumed to hit, like MetaForge
        base = base * pellets
        raw = base * self.zone_mult(w, zone) * self.falloff(w, rng)
        bare = raw * c["bare"]
        if armor:
            dmg = raw * c["vsTier"].get(armor["tier"], 1) * (1 - armor["reduction"] / 100 * c["penScalar"])
            # plate wears by base * plate multiplier per hit; once broken, hits do bare damage
            wear = base * self.falloff(w, rng) * c["plateHelmet" if armor["slot"] == "helmet" else "plateArmor"]
        else:
            dmg, wear = bare, 0
        hp, dur, shots, breaks = self.health, (armor or {}).get("durability", 0), 0, None
        while hp > 1e-9 and shots < 500:
            shots += 1
            if armor and dur > 1e-9:
                hp -= dmg
                dur -= wear
                if dur <= 1e-9:
                    breaks = shots
            else:
                hp -= bare
        rpm = w.get("roundsPerMinute") or 0
        vel = w.get("muzzleVelocity") or 0
        ttk = None
        if rpm:
            # 1.01 ~ drag slowing the bullet; reproduces MetaForge's TTK to the hundredth
            ttk = round((shots - 1) * 60 / rpm + (rng / vel * 1.01 if vel else 0) + 1e-9, 2)
        return {"dmg": dmg, "shots": shots, "ttk": ttk, "breaks": breaks}

    def plate_vs_fmj(self, cal, rnd):
        c, f = self.combat(cal, rnd), self.combat(cal, "FMJ")
        return c["plateArmor"] / f["plateArmor"] - 1 if f.get("plateArmor") else 0


# ---------- market helpers ----------
RANGES = {"7d": 7, "30d": 30, "90d": 90, "all": None}


def market_points(market, rng="30d"):
    pts = market["points"]
    days = RANGES.get(rng)
    if days:
        cutoff = pts[-1]["t"] - days * 86400000
        pts = [p for p in pts if p["t"] >= cutoff]
    return pts


def money(n):
    if n >= 1_000_000_000:
        return f"${n / 1e9:.2f}B"
    if n >= 1_000_000:
        return f"${n / 1e6:.2f}M"
    if n >= 10_000:
        return f"${n / 1e3:.0f}K"
    return f"${n:,.0f}"


# ---------------- attachments / recoil ----------------
RECOIL_SLOTS = ("Muzzle", "Underbarrel", "Magazine", "Stock", "Grip", "Pistolgrip", "Handguard", "Barrel")


class Attachments:
    """Attachment fit + exact stat modifiers (from /api/wardogs/attachment-stats)."""

    def __init__(self, database, stats):
        self.slot_labels = database.get("slotLabels", {})
        items = database.get("items", [])
        self.weapon_slots = {i["slug"]: i.get("slots") or [] for i in items if i.get("tab") == "weapons"}
        mods = stats.get("attachments", {})
        self.by_weapon = {}
        for a in items:
            if a.get("tab") != "attachments" or a.get("wip") or not a.get("slot"):
                continue
            m = {x["attribute"]: x["value"] for x in mods.get(a["slug"], {}).get("modifiers", [])
                 if x.get("op") == "multiply" and x.get("scope") == "weapon"}
            entry = {"slug": a["slug"], "name": a["name"], "slot": a["slot"], "icon": a.get("icon"),
                     "price": a.get("price"), "weight": a.get("weight") or 0,
                     "capacity": a.get("capacity"), "v": m.get("VerticalRecoilMultiplier", 1.0),
                     "h": m.get("HorizontalRecoilMultiplier", 1.0), "spread": m.get("SpreadMultiplier", 1.0),
                     "ads": m.get("AimTime", 1.0)}
            for w in a.get("fits") or []:
                self.by_weapon.setdefault(w, []).append(entry)

    def label(self, slot):
        return self.slot_labels.get(slot, slot)

    def best_recoil_build(self, w):
        """Best attachment per slot for recoil (vertical weighted 60%, horizontal 40%), ignoring optics."""
        options = self.by_weapon.get(w["slug"], [])
        slots = [s for s in (self.weapon_slots.get(w["slug"]) or []) if s in RECOIL_SLOTS]
        for s in sorted({o["slot"] for o in options if o["slot"] in RECOIL_SLOTS}):
            if s not in slots:
                slots.append(s)
        build = []
        for slot in slots:
            cands = [o for o in options if o["slot"] == slot]
            if not cands:
                continue
            score = lambda o: 0.6 * o["v"] + 0.4 * o["h"]  # climb is what you fight most, drift second
            best = min(cands, key=lambda o: (round(score(o), 4), o["ads"]))
            if score(best) >= 0.999:
                best = None  # nothing in this slot helps recoil
            pick = dict(best) if best else None
            alt = min(cands, key=lambda o: (o["h"], o["v"]))
            if pick and alt["slug"] != pick["slug"] and alt["h"] < pick["h"] - 0.04:
                pick["alt"] = alt  # better horizontal control, worth mentioning
            if pick and slot == "Magazine":
                pick["capacity_delta"] = (pick.get("capacity") or 0) - (w.get("magSize") or pick.get("capacity") or 0)
            build.append({"slot": slot, "label": self.label(slot), "pick": pick, "options": len(cands)})
        v = math.prod(b["pick"]["v"] for b in build if b["pick"]) if build else 1.0
        h = math.prod(b["pick"]["h"] for b in build if b["pick"]) if build else 1.0
        ads = math.prod(b["pick"]["ads"] for b in build if b["pick"]) if build else 1.0
        spread = math.prod(b["pick"]["spread"] for b in build if b["pick"]) if build else 1.0
        return {"slots": build, "v": v, "h": h, "ads": ads, "spread": spread}


def spray_path(w, v_mult=1.0, h_mult=1.0):
    """Cumulative recoil path in degrees [(x, y), ...] starting at (0, 0). Empty if no pattern."""
    pat = w.get("recoilPattern") or []
    vk = w.get("viewKickMultiplier") or 1.0
    attrs = w.get("attributes") or {}
    v_mult *= attrs.get("VerticalRecoilMultiplier", 1.0)
    h_mult *= attrs.get("HorizontalRecoilMultiplier", 1.0)
    pts, x, y = [(0.0, 0.0)], 0.0, 0.0
    for p in pat:
        x += p["x"] * vk * h_mult
        y += p["y"] * vk * v_mult
        pts.append((x, y))
    return pts


# ---------------- vehicles ----------------
_LI = re.compile(r"<li\b[^>]*>(.*?)</li>", re.S)
_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"^(?P<name>.+?)\s+(?P<dmg>[\d.,]+)\s+damage\s+(?:(?P<hits>\d+)\s+to\s+(?P<verb>destroy it|break)\s*(?P<zone>.*)|(?P<none>no effect).*)$")


def parse_destroy_list(html):
    """Read MetaForge's 'What destroys it' list from a vehicle page.
    Returns [{name, damage, hits, verb, zone}] in MetaForge's order (fastest first); hits None = no effect."""
    m = re.search(r'<div[^>]*role="tabpanel"[^>]*data-value="rounds"[^>]*>', html)
    if not m:
        return []
    i = m.start()
    j = html.find("</ul>", i)
    out = []
    for li in _LI.findall(html[i:j]):
        text = " ".join(_TAG.sub(" ", li).replace("&amp;", "&").split())
        m = _ROW.match(text)
        if not m:
            continue
        out.append({"name": m["name"], "damage": float(m["dmg"].replace(",", "")),
                    "hits": int(m["hits"]) if m["hits"] else None,
                    "verb": "destroy" if (m["verb"] or "").startswith("destroy") else ("break" if m["verb"] else None),
                    "zone": (m["zone"] or "").strip()})
    return out


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("winchester", "win"))


EXPLOSIVE_ITEMS = {"AT Mine": "at-mine", "Claymore": "claymore", "C4 Charge": "c4-charge",
                   "IED": "improvised-explosive-device", "Stingray": "stingray"}


def classify_sources(rows, b, items_by_slug):
    """Tag each 'what destroys it' row with who can use it: weapons you carry, deployables, or vehicles/artillery."""
    by_cal = {}
    for w in b.weapons.values():
        for k in {w.get("calibre"), *(w.get("supportedCalibres") or []), *(w.get("shells") or [])}:
            if k:
                by_cal.setdefault(k, []).append(w)
    keys = {}
    for k, c in b.calibres.items():
        keys.setdefault(_norm(k), k)
        if c.get("label"):
            keys.setdefault(_norm(c["label"]), k)
    out = []
    for r in rows:
        r = dict(r)
        item = items_by_slug.get(EXPLOSIVE_ITEMS.get(r["name"], ""))
        cal = keys.get(_norm(r["name"]))
        users = sorted(by_cal.get(cal, []), key=lambda w: w["name"]) if cal else []
        if item:
            r.update(kind="gear", users=[item["name"]], icon=item.get("icon"))
        elif users:
            r.update(kind="weapon", users=[w["name"] for w in users],
                     icon=items_by_slug.get(users[0]["slug"], {}).get("icon"))
        else:
            r.update(kind="vehicle", users=[], icon=None)
        out.append(r)
    return out
