# Discord Reaction-Role Bot

A small, self-contained Discord bot that assigns roles when members react to a
message — and removes them when the reaction is removed. Built with
[discord.py](https://github.com/Rapptz/discord.py).

It also ships two one-shot admin scripts to bootstrap a server: one that creates
permission-restricted channel categories, and one that copies role permissions.

> The example messages and channels are in Spanish (a gaming community: Tech,
> Gaming, Anime, Path of Exile, Diablo), but everything is configurable.

## What's in here

| File                 | Purpose                                                                 |
|----------------------|-------------------------------------------------------------------------|
| `keystroke_bot.py`   | The bot. Posts the reaction-role messages and listens for reactions.    |
| `setup_channels.py`  | One-shot script: creates POE/Diablo categories + channels, locked to roles. |
| `fetch_roles.py`     | One-shot script: copies the "Tech" role's permissions onto other roles. |
| `.env.example`       | Template for the configuration. Copy to `.env` and fill in.             |
| `Procfile`           | Process definition for Procfile-based hosts (Railway, Heroku, etc.).    |
| `requirements.txt`   | Python dependencies.                                                     |

## How it works

1. On startup the bot finds the `#elige-tu-rol` text channel.
2. It posts (or re-uses) two messages and adds emoji reactions to them. The
   message IDs are cached in `bot_state.json` so it doesn't re-post on restart.
3. When a member adds one of the tracked reactions, the matching role is added.
   Removing the reaction removes the role.

The emoji → role mapping lives in the `ROLES` and `MESSAGES` dicts at the top of
`keystroke_bot.py`.

## Setup

### 1. Create the bot application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create an application → **Bot** → **Reset Token** to get a token.
3. Under **Bot → Privileged Gateway Intents**, enable **Server Members Intent**
   (the bot needs it to assign roles).
4. Invite the bot to your server with the **Manage Roles** and **Manage Channels**
   permissions (OAuth2 → URL Generator → scopes: `bot`).

> The bot's own role must sit **above** the roles it assigns in the role list,
> or Discord will refuse the assignment.

### 2. Configure

```bash
cp .env.example .env
# edit .env and fill in your token, guild ID, and role IDs
```

Enable **Developer Mode** in Discord (Settings → Advanced) to copy IDs via
right-click.

### 3. Install and run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# load .env into your shell, then run
set -a && . ./.env && set +a
python keystroke_bot.py
```

(For the admin scripts, run `python setup_channels.py` or `python fetch_roles.py`
the same way — once each, then you're done with them.)

## Configuration reference

All configuration is via environment variables — nothing is hardcoded. See
`.env.example` for the full list.

## License

See [LICENSE](LICENSE).
