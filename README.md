# WARDOGS Discord bot

Discord bot for [WARDOGS](https://store.steampowered.com/) built on MetaForge's data.

| Command | What it does |
|---|---|
| `/gold` | Today's cash-per-gold-bar rate with 1d / 7d / 30d change |
| `/cost bars:30` | Cash cost of N gold bars today, at the all-time low and high |
| `/chart 7d\|30d\|90d\|all` | Gold price history graph |
| `/compare m4 ak74 [weapon3]` | Side-by-side card, shots to kill vs every armor tier; zone dropdown + FMJ/HP/AP buttons |
| `/ammo deagle` | FMJ vs HP vs AP (or slug vs buckshot) card for one weapon |

Damage math reproduces metaforge.app/wardogs/ballistics (armor reduction × penetration, plate durability, pellets, falloff).

## Run (Docker)

```bash
git clone <this repo> wardogs-bot && cd wardogs-bot
cp .env.example .env && nano .env
docker compose up -d --build
```

## Update

```bash
git pull && docker compose up -d --build
```

Data: [MetaForge](https://metaforge.app/wardogs). Fonts: Inter (SIL OFL, see `fonts/LICENSE.txt`).
