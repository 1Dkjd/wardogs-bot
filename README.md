# WARDOGS Discord bot

Discord bot for [WARDOGS](https://store.steampowered.com/) built on MetaForge's data.

| Command | What it does |
|---|---|
| `/gold` | Gold bar rate card: 1D/7D/30D change, buy signal, skin prices |
| `/cost bars:30` | Cash cost of N bars (today / all-time low / high) and which Gold Market items fit |
| `/chart` | Gold price history card with 7D / 30D / 90D / ALL buttons |
| `/compare m4 ak74 [weapon3]` | Side-by-side card, shots to kill vs every armor tier; zone, round and distance buttons |
| `/ammo deagle` | FMJ vs HP vs AP (or slug vs buckshot) card; zone and distance buttons |
| `/weapon m4` | Spray pattern, stock vs best build, and the best recoil attachment per slot |
| `/vehicle l2a6` | What kills a vehicle on foot (mines, launchers, C4...) and how many hits, plus bullets and vehicle weapons |
| `/changes` | Latest balance patch the bot spotted |
| `/help` | Command overview |

**Balance-patch alerts:** every 3 hours the bot snapshots ~900 stats from MetaForge (weapon fire rate, recoil,
ammo damage and penetration, armor, attachments, vehicle health, prices). When anything changes it posts a
"Balance changes" card to `PATCH_CHANNEL_ID` (or `DAILY_CHANNEL_ID`).

Works in any server it's invited to, and as a **user install** (add it to your own account and use the
commands anywhere, including DMs).

Damage math reproduces metaforge.app/wardogs/ballistics (armor reduction × penetration, plate durability, pellets, falloff).
Recoil uses each weapon's 30-shot pattern × view kick and the exact attachment multipliers from MetaForge.

## Run (Docker)

```bash
git clone <this repo> wardogs-bot && cd wardogs-bot
cp .env.example .env && nano .env   # token, optional DAILY_CHANNEL_ID for an automatic daily gold card
docker compose up -d --build
```

## Invite links

In the Discord Developer Portal → your app → **Installation**, tick **Guild Install** and **User Install**.
Guild Install scopes: `bot`, `applications.commands`; permissions: Send Messages, Embed Links, Attach Files.
Share the install link it gives you. Keep **Bot → Public Bot** on so others can add it.

## Update

```bash
git pull && docker compose up -d --build
```

Data: [MetaForge](https://metaforge.app/wardogs). Fonts: Inter (SIL OFL, see `fonts/LICENSE.txt`).
