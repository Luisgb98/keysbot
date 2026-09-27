# Discord Button-Role Bot

A Discord bot that assigns roles when members click a button — and removes them
when they click it again. It runs as a **single stateless Cloudflare Worker**,
not a 24/7 process: Discord delivers button clicks as signed HTTP webhooks, so
there's nothing to keep alive and it fits comfortably in Cloudflare's free tier.

The same Worker also **announces streams and videos**: Twitch tells it when the
channel goes live, and [keystroke-hub](https://github.com/Luisgb98/keystroke-hub)
tells it when a video is published — both as signed webhooks too — and it posts
to `#directos` / `#videos`, pinging the members who opted in with a button.

It also ships one-shot admin scripts to bootstrap a server: one that posts the
role messages, one that creates permission-restricted channel categories, and
one that copies role permissions.

> The example messages and channels are in Spanish (a gaming community: Tech,
> Gaming, Anime, Path of Exile, Diablo, AION 2, WoW Forever), but everything is
> configurable.

## What's in here

| File                  | Purpose                                                                     |
|-----------------------|-----------------------------------------------------------------------------|
| `worker/src/index.js` | The bot. Verifies signatures, toggles roles on button clicks, routes.       |
| `worker/src/twitch.js`| `POST /twitch`: Twitch EventSub → live announcement in `#directos`.         |
| `worker/src/videos.js`| `POST /videos`: keystroke-hub → video announcement in `#videos`.            |
| `worker/test/`        | `npm test` (Node's built-in runner, fake Discord/Twitch behind `fetch`).    |
| `worker/wrangler.toml`| Worker config: guild, role allowlist, channels, roles to ping.              |
| `post_messages.py`    | One-shot script: posts (or edits) the button messages.                      |
| `setup_roles.py`      | One-shot script: creates the game and notification button roles.           |
| `subscribe_twitch.py` | One-shot script: subscribes the Worker to Twitch's `stream.online`.         |
| `upload_emojis.py`    | One-shot script: uploads `local/emojis/*.png` as app + server emojis.       |
| `setup_channels.py`   | One-shot script: creates each game's category + channels, locked to roles.  |
| `fetch_roles.py`      | One-shot script: copies the "Tech" role's permissions onto other roles.     |
| `.env.example`        | Template for the configuration. Copy to `.env` and fill in.                 |

## How it works

1. `post_messages.py` posts the messages to `#elige-tu-rol`, each with buttons
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

## Announcements

Members opt in with the **Twitch** and **Vídeos** buttons (🔔 Notificaciones in
`#elige-tu-rol`). Neither role is mentionable by members, so only the bot pings
them. Both channels are read-only.

**Live** — `stream.online` from Twitch EventSub → `#directos`:
*"@Twitch ¡KeystrokeG está en directo!"* with the title, game and link. A second
`stream.online` within `LIVE_COOLDOWN_MINUTES` of the last announcement is a
reconnect and stays quiet.

**Videos** — keystroke-hub, when a video is marked Published → `#videos`:
*"@Vídeos ¡Nuevo vídeo!"* with the title and its YouTube, YouTube Shorts, TikTok
and Instagram links (the first one gets Discord's preview; TikTok and Instagram
links lose their tracking query). Nothing is stored: before posting,
the Worker looks for the video's links in the last 50 messages of `#videos`, so
a retry never posts twice.

### The `POST /videos` contract

```http
POST https://keysbot.<subdomain>.workers.dev/videos
Content-Type: application/json
X-Keysbot-Timestamp: 1790000000
X-Keysbot-Signature: sha256=<hex HMAC-SHA256(VIDEOS_HMAC_SECRET, timestamp + "." + body)>

{
  "id": "<idea uuid>",
  "title": "Build de Gladiador para AION 2",
  "links": {
    "youtube": "https://www.youtube.com/watch?v=…",
    "youtube_shorts": "https://youtube.com/shorts/…",
    "tiktok": "https://www.tiktok.com/@…/video/…",
    "instagram": "https://www.instagram.com/reel/…"
  }
}
```

- The timestamp is unix seconds and must be within 5 minutes of the Worker's
  clock. The signature covers the **exact** body bytes sent.
- `links` needs at least one https link on its own platform's domain; empty or
  `null` platforms are skipped, unknown ones are rejected.

| Answer | Body                                          | Meaning                                    |
|--------|-----------------------------------------------|--------------------------------------------|
| `201`  | `{"status":"announced","messageId":"…"}`         | Posted now.                                |
| `200`  | `{"status":"already-announced","messageId":"…"}` | One of its links is already in `#videos`.  |
| `401`  | `{"error":"invalid-signature"}`               | Bad signature or stale timestamp.          |
| `400`  | `{"error":"invalid-json"}`                    |                                            |
| `422`  | `{"error":"validation","issues":["…"]}`       | Every problem at once. Don't retry as is.  |
| `502`  | `{"error":"discord-unavailable"}`             | Discord failed; safe to retry.             |

### Setting it up

1. `python setup_roles.py`, `python setup_channels.py` (creates `#directos` and
   `#videos` in `👋 comunidad`), add the IDs to `worker/wrangler.toml`, then
   `python post_messages.py`.
2. Worker secrets: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`,
   `TWITCH_EVENTSUB_SECRET` and `VIDEOS_HMAC_SECRET` (`openssl rand -hex 32` for
   the last two), then `npx wrangler deploy`.
3. Fill the Twitch block of `.env` and run `python subscribe_twitch.py`. Twitch
   verifies the Worker on the spot; the script prints the channel's user ID —
   put it in `TWITCH_BROADCASTER_ID` and deploy again.
4. Give keystroke-hub the Worker URL and the same `VIDEOS_HMAC_SECRET`.

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
| `LIVE_CHANNEL_ID`, `ROLE_TWITCH_ID` | Worker var | `#directos` and the role it pings.            |
| `VIDEOS_CHANNEL_ID`, `ROLE_VIDEOS_ID` | Worker var | `#videos` and the role it pings.            |
| `TWITCH_BROADCASTER_ID` | Worker var            | Twitch user ID whose streams are announced.    |
| `LIVE_COOLDOWN_MINUTES` | Worker var            | Reconnect window, default 120.                 |
| `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | `.env` + Worker secret | Twitch app credentials.   |
| `TWITCH_EVENTSUB_SECRET` | `.env` + Worker secret | Signs Twitch's webhooks.                    |
| `VIDEOS_HMAC_SECRET` | Worker secret + hub      | Signs keystroke-hub's `POST /videos`.          |
| `ROLE_*`             | `.env`                   | Role IDs used by the one-shot scripts.         |

## License

See [LICENSE](LICENSE).
