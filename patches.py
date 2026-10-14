"""Balance-patch detection: snapshot every stat MetaForge publishes, diff against the last snapshot."""
import json
import os
import time

# stat key -> (label, higher_is_better). higher_is_better=None means "just show it".
STATS = {
    "dmg": ("Damage", True), "pellets": ("Pellets", True), "rpm": ("Fire rate", True),
    "vel": ("Velocity", True), "range": ("Effective range", True), "mag": ("Magazine", True),
    "moa": ("Accuracy (MOA)", False), "climb": ("Recoil climb", False), "kick": ("View kick", False),
    "flesh": ("vs flesh", True), "pen": ("Armor blocks", False), "plate": ("Plate wear", True),
    "reduction": ("Blocks", True), "durability": ("Durability", True), "health": ("Health", True),
    "v": ("Vertical recoil", False), "h": ("Horizontal recoil", False), "ads": ("ADS time", False),
    "spread": ("Spread", False), "price": ("Price", False), "zone": ("Hit multiplier", True),
}
ROUNDS = {"FMJ": "FMJ", "HollowPoint": "HP", "ArmorPiercing": "AP"}


def snapshot(ballistics, database, attachment_stats, vehicles=None):
    """Flatten everything into {key: {"group", "item", "stat", "value"}}."""
    snap = {}

    def put(group, item, stat, value, sub=None):
        if value is None:
            return
        key = f"{group}|{item}|{sub or ''}|{stat}"
        snap[key] = {"group": group, "item": item + (f" · {sub}" if sub else ""), "stat": stat,
                     "value": round(float(value), 4)}

    for w in ballistics.get("weapons", []):
        n = w["name"]
        put("Weapons", n, "rpm", w.get("roundsPerMinute"))
        put("Weapons", n, "vel", w.get("muzzleVelocity"))
        put("Weapons", n, "range", w.get("effectiveRange"))
        put("Weapons", n, "mag", w.get("magSize"))
        put("Weapons", n, "moa", w.get("accuracyMoa"))
        put("Weapons", n, "kick", w.get("viewKickMultiplier"))
        pat = w.get("recoilPattern") or []
        if pat:
            put("Weapons", n, "climb", sum(p["y"] for p in pat) * (w.get("viewKickMultiplier") or 1))
    for k, c in ballistics.get("calibres", {}).items():
        n = c.get("label") or k
        put("Ammo", n, "dmg", c.get("baseDamage"))
        if (c.get("pellets") or 1) > 1:
            put("Ammo", n, "pellets", c.get("pellets"))
        for r, cb in (c.get("combat") or {}).items():
            short = ROUNDS.get(r, r)
            put("Ammo", n, "flesh", cb.get("bare"), short)
            put("Ammo", n, "pen", cb.get("penScalar"), short)
            put("Ammo", n, "plate", cb.get("plateArmor"), short)
    for a in ballistics.get("armour", []):
        put("Armor", a["name"], "reduction", a.get("reduction"))
        put("Armor", a["name"], "durability", a.get("durability"))
    for cls, zones in (ballistics.get("hitboxes") or {}).items():
        for z, m in zones.items():
            if z in ("head", "torso_upper", "torso_middle"):
                put("Hit zones", cls, "zone", m, z.replace("_", " ").title())

    items = {i["slug"]: i for i in database.get("items", []) if not i.get("wip")}
    for i in items.values():
        if i.get("price") is not None and i.get("tab") in ("weapons", "armor", "throwables", "equipment",
                                                           "deployables", "attachments", "vehicles"):
            put("Prices", i["name"], "price", i["price"])
        if i.get("tab") == "vehicles" and (i.get("vehicle") or {}).get("health"):
            put("Vehicles", i["name"], "health", i["vehicle"]["health"])
    for slug, a in (attachment_stats or {}).get("attachments", {}).items():
        name = items.get(slug, {}).get("name") or slug
        for m in a.get("modifiers", []):
            stat = {"VerticalRecoilMultiplier": "v", "HorizontalRecoilMultiplier": "h", "AimTime": "ads",
                    "SpreadMultiplier": "spread"}.get(m.get("attribute"))
            if stat and m.get("op") == "multiply":
                put("Attachments", name, stat, m.get("value"))
    return snap


def diff(old, new):
    """[{group, item, stat, label, old, new, pct, good}] for every changed, added or removed stat."""
    out = []
    for key in sorted(set(old) | set(new)):
        o, n = old.get(key), new.get(key)
        if o and n and abs(o["value"] - n["value"]) < 1e-6:
            continue
        ref = n or o
        label, hib = STATS.get(ref["stat"], (ref["stat"], None))
        ov, nv = (o or {}).get("value"), (n or {}).get("value")
        pct = (nv - ov) / ov if ov not in (None, 0) and nv is not None else None
        good = None
        if ov is not None and nv is not None and hib is not None:
            good = (nv > ov) == hib
        out.append({"group": ref["group"], "item": ref["item"], "stat": ref["stat"], "label": label,
                    "old": ov, "new": nv, "pct": pct, "good": good})
    return out


class PatchWatcher:
    def __init__(self, data_dir="/data"):
        self.snap_file = os.path.join(data_dir, "snapshot.json")
        self.last_file = os.path.join(data_dir, "last_patch.json")

    def _load(self, path):
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _save(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)

    def check(self, snap):
        """Compare with the stored snapshot. Returns the list of changes (empty on first run / no change)."""
        old = self._load(self.snap_file)
        if old is None:
            self._save(self.snap_file, snap)
            return []
        changes = diff(old, snap)
        if changes:
            self._save(self.last_file, {"detected": time.time(), "changes": changes})
        self._save(self.snap_file, snap)
        return changes

    def last(self):
        return self._load(self.last_file)
