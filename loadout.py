"""Turn a saved loadout spec (slugs + quantities) into a priced, drawable kit."""
import math

ROUND_TYPES = {"FMJ": "Standard (FMJ)", "HollowPoint": "Flesh Damage (HP)", "ArmorPiercing": "Armor Piercing (AP)"}
ROUND_SHORT_LABEL = {"FMJ": "FMJ", "HollowPoint": "HP", "ArmorPiercing": "AP"}


class Catalog:
    """Buyable items from MetaForge's item database, indexed for loadouts."""

    def __init__(self, database):
        items = [i for i in database.get("items", []) if not i.get("wip")]
        self.by_slug = {i["slug"]: i for i in items}
        self.ammo = [i for i in items if i.get("tab") == "ammunition" and not i["slug"].endswith("-t")]

    def get(self, slug):
        return self.by_slug.get(slug)

    def by_equip(self, *slots, tab=None):
        out = [i for i in self.by_slug.values() if i.get("price") is not None
               and (tab is None or i.get("tab") == tab)
               and (not slots or set(slots) & set(i.get("equipSlots") or []))]
        return sorted(out, key=lambda i: i["name"])

    def gear(self):
        return sorted([i for i in self.by_slug.values() if i.get("price") is not None and i.get("quickSlot")
                       and i.get("tab") in ("throwables", "equipment", "deployables")], key=lambda i: i["name"])

    def ammo_for(self, weapon, rnd):
        cal = weapon.get("calibre")
        want = ROUND_TYPES.get(rnd)
        pool = [a for a in self.ammo if a.get("calibre") == cal]
        return next((a for a in pool if a.get("roundType") == want), None) or (pool[0] if pool else None)


def _ammo(cat, weapon, rnd, rounds):
    if not rounds:
        return None
    a = cat.ammo_for(weapon, rnd)
    if not a:
        return None
    per = a.get("amount") or 10
    used = rnd if a.get("roundType") == ROUND_TYPES.get(rnd) else "FMJ"
    return {"item": a, "rounds": rounds, "price": math.ceil(rounds / per) * (a.get("price") or 0),
            "round": used, "label": f"{weapon.get('calibreLabel') or ''} {ROUND_SHORT_LABEL.get(used, used)}".strip(),
            "weight": (a.get("weight") or 0) * math.ceil(rounds / per)}


def resolve(spec, cat, A):
    """spec: {name, author, tags, primary, attachments[], ammo, rounds, sidearm, sidearm_rounds,
    armor, helmet, gear{slug: qty}} -> kit dict for cards.loadout_card."""
    kit = {"name": spec.get("name") or "Loadout", "author": spec.get("author"), "tags": spec.get("tags") or []}
    total, weight, count = 0, 0.0, 0

    def add(it, qty=1, price=None, wt=None):
        nonlocal total, weight, count
        total += (it.get("price") or 0) * qty if price is None else price
        weight += (it.get("weight") or 0) * qty if wt is None else wt
        count += 1

    prim = cat.get(spec.get("primary"))
    if prim:
        options = {o["slug"]: o for o in A.by_weapon.get(prim["slug"], [])}
        atts = [options[s] for s in spec.get("attachments") or [] if s in options]
        ammo = _ammo(cat, prim, spec.get("ammo", "FMJ"), spec.get("rounds", 120))
        kit["primary"] = {"item": prim, "attachments": atts, "ammo": ammo}
        add(prim)
        for a in atts:
            add(a)
        if ammo:
            add(ammo["item"], price=ammo["price"], wt=ammo["weight"])
    side = cat.get(spec.get("sidearm"))
    if side:
        ammo = _ammo(cat, side, spec.get("sidearm_ammo", "FMJ"), spec.get("sidearm_rounds", 30))
        kit["sidearm"] = {"item": side, "ammo": ammo}
        add(side)
        if ammo:
            add(ammo["item"], price=ammo["price"], wt=ammo["weight"])
    for key in ("armor", "helmet"):
        it = cat.get(spec.get(key))
        kit[key] = it
        if it:
            add(it)
    kit["gear"] = []
    for slug, qty in (spec.get("gear") or {}).items():
        it = cat.get(slug)
        if it and qty > 0:
            kit["gear"].append({"item": it, "qty": qty})
            add(it, qty)
    kit.update(total=total, weight=weight, count=count)
    return kit


def icon_names(kit):
    names = []
    p = kit.get("primary") or {}
    for it in [p.get("item"), *(p.get("attachments") or []), (p.get("ammo") or {}).get("item"),
               (kit.get("sidearm") or {}).get("item"), ((kit.get("sidearm") or {}).get("ammo") or {}).get("item"),
               kit.get("armor"), kit.get("helmet"), *[g["item"] for g in kit.get("gear") or []]]:
        if it and it.get("icon"):
            names.append(it["icon"])
    return names
