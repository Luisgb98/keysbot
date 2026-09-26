# Discord Button-Role Bot

A Discord bot that assigns roles when members click a button — and removes them
when they click it again. It runs as a **single stateless Cloudflare Worker**,
not a 24/7 process: Discord delivers button clicks as signed HTTP webhooks, so
there's nothing to keep alive and it fits comfortably in Cloudflare's free tier.

It also ships one-shot admin scripts to bootstrap a server: one that posts the
role messages, one that creates permission-restricted channel categories, and
one that copies role permissions.

> The example messages and channels are in Spanish (a gaming community: Tech,
> Gaming, Anime, Path of Exile, Diablo, AION 2, WoW Forever), but everything is
> configurable.

## What's in here

| File                  | Purpose                                                                     |
|-----------------------|-----------------------------------------------------------------------------|
| `worker/src/index.js` | The bot. Verifies signatures, toggles roles on button clicks.               |
| `worker/wrangler.toml`| Worker config: `GUILD_ID`, `ALLOWED_ROLE_IDS`, `LOG_CHANNEL_ID`.            |
| `post_messages.py`    | One-shot script: posts (or edits) the two button messages.                  |
| `setup_roles.py`      | One-shot script: creates the AION 2 / WoW Forever button roles.             |
| `upload_emojis.py`    | One-shot script: uploads `local/emojis/*.png` as app + server emojis.       |
| `setup_channels.py`   | One-shot script: creates each game's category + channels, locked to roles.  |
| `fetch_roles.py`      | One-shot script: copies the "Tech" role's permissions onto other roles.     |
| `.env.example`        | Template for the configuration. Copy to `.env` and fill in.                 |

## How it works

1. `post_messages.py` posts two messages to `#elige-tu-rol`, each with buttons
   whose `custom_id` is `role:<ROLE_ID>`. The message IDs are cached in
   `bot_state.json`, so re-running edits them in place instead of duplicating.
2. When a member clicks a button, Discord POSTs a **signed interaction** to the
   Worker's URL.
3. The Worker verifies the Ed25519 signature, checks the role ID against
   `ALLOWED_ROLE_IDS`, and toggles it — the member's current roles arrive in the
   payload, so it's a single `PUT`/`DELETE` REST call.
4. It replies with an ephemeral confirmation ("✅ Rol **Tech** añadido") and,
   if `LOG_CHANNEL_ID` is set, logs a line to `#keysbot`.

The role → button mapping lives in the `ROLES` and `MESSAGES` dicts at the top
of `post_messages.py`.

## Setup

### 1. Create the bot application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create an application → **Bot** → **Reset Token** to get a token.
3. Copy the app's **Public Key** from **General Information** — the Worker needs it.
4. Invite the bot with the **Manage Roles** and **Manage Channels** permissions
   (OAuth2 → URL Generator → scopes: `bot`).

> The bot's own role must sit **above** the roles it assigns in the role list,
> or Discord will refuse the assignment.
>
> No privileged intents are needed any more — the interaction payload carries
> the member's roles.

### 2. Configure

```bash
cp .env.example .env
# edit .env and fill in your token, public key, guild ID, and role IDs
```

Enable **Developer Mode** in Discord (Settings → Advanced) to copy IDs via
right-click.

### 3. Deploy the Worker

```bash
cd worker
npm install
npx wrangler login          # free Cloudflare account
```

Fill in the `[vars]` block in `wrangler.toml` (`GUILD_ID`, `ALLOWED_ROLE_IDS`
as a comma-separated list of the five role IDs, and `LOG_CHANNEL_ID`), then:

```bash
npx wrangler deploy
npx wrangler secret put DISCORD_TOKEN
npx wrangler secret put DISCORD_PUBLIC_KEY
```

`deploy` prints the Worker's URL (`https://keysbot.<subdomain>.workers.dev`).

### 4. Point Discord at the Worker

Paste that URL into **Developer Portal → General Information → Interactions
Endpoint URL** and save. Discord sends a signed PING and only accepts the URL if
the Worker answers correctly — a successful save proves signature verification
works.

### 5. Post the messages

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
set -a && . ./.env && set +a

python post_messages.py --test   # private #keysbot-test channel first
```

`--test` creates a `#keysbot-test` channel visible only to you (the server
owner) and the bot. Click all five buttons and check that roles toggle, the
ephemeral replies appear, and log lines land in `#keysbot`. Watch the Worker
live with `npx wrangler tail` from `worker/` while you click.

Once it all works:

```bash
python post_messages.py          # publishes to #elige-tu-rol
```

Then delete `#keysbot-test`.

(For the other admin scripts, run `python setup_channels.py` or
`python fetch_roles.py` the same way — once each, then you're done with them.)

### Adding a game (AION 2 / WoW Forever)

Each game gets a **button role** that unlocks its category (news, general,
guides, experiments, per-class builds…).

1. `python setup_roles.py` — creates the two roles (skips any that exist) and
   prints their IDs. Paste them into `.env`.
2. Append both role IDs to `ALLOWED_ROLE_IDS` in `worker/wrangler.toml` and
   `npx wrangler deploy`.
3. Re-source `.env`, then `python setup_channels.py` — only creates what's
   missing, existing categories just get their permissions re-applied.
4. Drop the game's logo in `local/emojis/<name>.png` (128×128, git-ignored —
   logos are trademarks and this repo is public), run `python upload_emojis.py`,
   and use `:<name>:` in `MESSAGES` in `post_messages.py`.
5. `python post_messages.py --test`, check the new buttons, then
   `python post_messages.py` — edits the live message in place.

## Configuration reference

All configuration is via environment variables — nothing is hardcoded. See
`.env.example` for the scripts, and `worker/wrangler.toml` for the Worker.

| Name                 | Where                    | Purpose                                        |
|----------------------|--------------------------|------------------------------------------------|
| `DISCORD_TOKEN`      | `.env` + Worker secret   | Bot token.                                     |
| `DISCORD_PUBLIC_KEY` | Worker secret            | Verifies Discord's request signatures.         |
| `GUILD_ID`           | `.env` + Worker var      | The server.                                    |
| `ALLOWED_ROLE_IDS`   | Worker var               | Comma-separated allowlist of toggleable roles. |
| `LOG_CHANNEL_ID`     | `.env` + Worker var      | `#keysbot` log channel; empty disables logging.|
| `ROLE_*`             | `.env`                   | Role IDs used by the one-shot scripts.         |

## License

See [LICENSE](LICENSE).
