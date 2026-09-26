"""One-shot script: publish the role messages as button messages.

Replaces the posting logic that used to live in keystroke_bot.py's on_ready.
Run it once (like setup_channels.py) — the actual role toggling is handled by
the Cloudflare Worker in worker/, which receives button clicks as webhooks.

    python post_messages.py --test    # post to a private #keysbot-test channel
    python post_messages.py           # post to #elige-tu-rol

Message IDs are cached in bot_state.json, so re-running edits the existing
messages in place instead of posting duplicates.
"""

import argparse
import json
import os
import re
import sys

import requests

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = os.environ["GUILD_ID"]

API = "https://discord.com/api/v10"
HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs, 10)",
    "Content-Type": "application/json",
}

LIVE_CHANNEL = "elige-tu-rol"
TEST_CHANNEL = "keysbot-test"

VIEW_CHANNEL = 1024
SEND_MESSAGES = 2048

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state.json")

# ── Role IDs ──────────────────────────────────────────────────────────────────
ROLES = {
    "tech": os.environ["ROLE_TECH"],
    "gaming": os.environ["ROLE_GAMING"],
    "anime": os.environ["ROLE_ANIME"],
    "poe": os.environ["ROLE_POE"],
    "diablo": os.environ["ROLE_DIABLO"],
    "aion2": os.environ["ROLE_AION2"],
    "wow": os.environ["ROLE_WOW"],
    "twitch": os.environ["ROLE_TWITCH"],
    "videos": os.environ["ROLE_VIDEOS"],
}

# ── Messages to post ──────────────────────────────────────────────────────────
# Each button's custom_id is "role:<ROLE_ID>" — the worker parses that, checks it
# against ALLOWED_ROLE_IDS, and toggles the role.
# ":name:" refers to one of the app's own emojis (uploaded by upload_emojis.py),
# both in the text and on the buttons; anything else is a plain Unicode emoji.
# "#name" in the text becomes a clickable mention of that text channel.
FOOTER = "*Pulsa un botón para obtener el rol. Púlsalo de nuevo para quitarlo.*"

MESSAGES = {
    "msg1": {
        "text": (
            "🎭 **Elige tu comunidad de interés**\n\n"
            "💻 ─ **Tech** · Tecnología y programación\n"
            "🎮 ─ **Gaming** · Videojuegos en general\n"
            "🎌 ─ **Anime** · Series y manga\n\n"
            f"{FOOTER}"
        ),
        "buttons": [
            ("💻", "Tech", "tech"),
            ("🎮", "Gaming", "gaming"),
            ("🎌", "Anime", "anime"),
        ],
    },
    "msg2": {
        "text": (
            "⚔️ **Elige tu juego**\n\n"
            ":poe: ─ **Path of Exile** · Accede a los canales de POE\n"
            ":diablo: ─ **Diablo** · Accede a los canales de Diablo\n"
            ":aion2: ─ **AION 2** · Accede a los canales de AION 2\n"
            ":wowforever: ─ **WoW Forever** · Accede a los canales de WoW Forever\n\n"
            f"{FOOTER}"
        ),
        "buttons": [
            (":poe:", "Path of Exile", "poe"),
            (":diablo:", "Diablo", "diablo"),
            (":aion2:", "AION 2", "aion2"),
            (":wowforever:", "WoW Forever", "wow"),
        ],
    },
    "msg3": {
        "text": (
            "🔔 **Notificaciones**\n\n"
            ":twitch: ─ **Twitch** · Te aviso en #directos cuando empiece directo\n"
            ":youtube: ─ **Vídeos** · Te aviso en #videos de cada vídeo nuevo "
            "en :youtube: YouTube, :tiktok: TikTok e :instagram: Instagram\n\n"
            f"{FOOTER}"
        ),
        "buttons": [
            (":twitch:", "Twitch", "twitch"),
            (":youtube:", "Vídeos", "videos"),
        ],
    },
}


def api(method, path, body=None):
    """Returns (payload, error_string). Mirrors the helper in setup_channels.py."""
    res = requests.request(method, API + path, headers=HEADERS, json=body, timeout=30)
    if not res.ok:
        return None, f"HTTP {res.status_code}: {res.text}"
    if res.status_code == 204 or not res.content:
        return {}, None
    return res.json(), None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_app_emojis():
    """name → id of the application's own emojis."""
    app, err = api("GET", "/applications/@me")
    if err:
        sys.exit(f"✗ No se pudo leer la aplicación: {err}")
    emojis, err = api("GET", f"/applications/{app['id']}/emojis")
    if err:
        sys.exit(f"✗ No se pudieron listar los emojis de la app: {err}")
    return {e["name"]: e["id"] for e in emojis["items"]}


def custom_name(emoji):
    """':poe:' → 'poe'; None for a Unicode emoji."""
    if len(emoji) > 2 and emoji.startswith(":") and emoji.endswith(":"):
        return emoji[1:-1]
    return None


def button_emoji(emoji, app_emojis):
    name = custom_name(emoji)
    if name is None:
        return {"name": emoji}
    if name not in app_emojis:
        sys.exit(f"✗ El emoji '{name}' no está en la app. Ejecuta upload_emojis.py primero.")
    return {"id": app_emojis[name], "name": name}


def render_text(text, app_emojis, channel_ids):
    for name, emoji_id in app_emojis.items():
        text = text.replace(f":{name}:", f"<:{name}:{emoji_id}>")
    return re.sub(
        r"#([a-z0-9-]+)",
        lambda m: f"<#{channel_ids[m[1]]}>" if m[1] in channel_ids else m[0],
        text,
    )


def components_for(msg_def, app_emojis):
    """One action row holding this message's buttons (max 5 per row — we have at most 4)."""
    return [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,          # button
                    "style": 2,         # secondary (grey)
                    "label": label,
                    "emoji": button_emoji(emoji, app_emojis),
                    "custom_id": f"role:{ROLES[role_key]}",
                }
                for emoji, label, role_key in msg_def["buttons"]
            ],
        }
    ]


def text_channels():
    channels, err = api("GET", f"/guilds/{GUILD_ID}/channels")
    if err:
        sys.exit(f"✗ No se pudieron listar los canales: {err}")
    return [c for c in channels if c["type"] == 0]


def find_channel(name):
    return next((c for c in text_channels() if c["name"] == name), None)


def channel_ids_by_name():
    """name → id for text channels whose name is unique ("general" isn't)."""
    channels = text_channels()
    names = [c["name"] for c in channels]
    return {c["name"]: c["id"] for c in channels if names.count(c["name"]) == 1}


def ensure_test_channel():
    """Create (or reuse) #keysbot-test, visible only to the server owner and the bot."""
    existing = find_channel(TEST_CHANNEL)
    if existing:
        print(f"  ↩ Canal #{TEST_CHANNEL} ya existe (ID: {existing['id']})")
        return existing

    guild, err = api("GET", f"/guilds/{GUILD_ID}")
    if err:
        sys.exit(f"✗ No se pudo leer el servidor: {err}")
    owner_id = guild["owner_id"]

    me, err = api("GET", "/users/@me")
    if err:
        sys.exit(f"✗ No se pudo leer la identidad del bot: {err}")

    allow = str(VIEW_CHANNEL | SEND_MESSAGES)
    overwrites = [
        {"id": GUILD_ID, "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL)},  # @everyone
        {"id": owner_id, "type": 1, "allow": allow, "deny": "0"},              # dueño
        {"id": me["id"], "type": 1, "allow": allow, "deny": "0"},              # el bot
    ]

    channel, err = api("POST", f"/guilds/{GUILD_ID}/channels", {
        "name": TEST_CHANNEL,
        "type": 0,
        "topic": "Canal de pruebas de keysbot — solo visible para el dueño y el bot.",
        "permission_overwrites": overwrites,
    })
    if err:
        sys.exit(f"✗ No se pudo crear #{TEST_CHANNEL}: {err}")

    print(f"  ✓ Canal #{TEST_CHANNEL} creado (ID: {channel['id']}) — visible solo para el dueño")
    return channel


def publish(channel_id, state, key, msg_def, app_emojis, channel_ids):
    """Edit the saved message if it still exists, otherwise post a new one."""
    payload = {
        "content": render_text(msg_def["text"], app_emojis, channel_ids),
        "components": components_for(msg_def, app_emojis),
    }
    saved_id = state.get(key)

    if saved_id:
        _, err = api("GET", f"/channels/{channel_id}/messages/{saved_id}")
        if err is None:
            _, err = api("PATCH", f"/channels/{channel_id}/messages/{saved_id}", payload)
            if err:
                sys.exit(f"✗ No se pudo editar '{key}': {err}")
            print(f"  ↩ Mensaje '{key}' actualizado (ID: {saved_id})")
            # An edited message may still carry reactions from the old bot —
            # clear them so nobody clicks an emoji that no longer does anything.
            api("DELETE", f"/channels/{channel_id}/messages/{saved_id}/reactions")
            return
        print(f"  ! Mensaje '{key}' guardado ya no existe, se publicará de nuevo")

    msg, err = api("POST", f"/channels/{channel_id}/messages", payload)
    if err:
        sys.exit(f"✗ No se pudo publicar '{key}': {err}")

    state[key] = msg["id"]
    save_state(state)
    print(f"  ✓ Mensaje '{key}' publicado (ID: {msg['id']})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test",
        action="store_true",
        help=f"publicar en #{TEST_CHANNEL} (privado, solo dueño + bot) en vez de #{LIVE_CHANNEL}",
    )
    args = parser.parse_args()

    if args.test:
        channel = ensure_test_channel()
        prefix = "test_"
    else:
        channel = find_channel(LIVE_CHANNEL)
        if not channel:
            sys.exit(f"✗ Canal '#{LIVE_CHANNEL}' no encontrado. Créalo primero.")
        print(f"  → Publicando en #{LIVE_CHANNEL} (ID: {channel['id']})")
        prefix = ""

    app_emojis = load_app_emojis()
    channel_ids = channel_ids_by_name()
    state = load_state()
    for key, msg_def in MESSAGES.items():
        publish(channel["id"], state, prefix + key, msg_def, app_emojis, channel_ids)

    print("\nListo. Recuerda que el worker debe tener estos IDs en ALLOWED_ROLE_IDS:")
    print("  " + ",".join(ROLES.values()))


if __name__ == "__main__":
    main()
