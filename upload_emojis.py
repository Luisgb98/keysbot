"""One-shot script: upload the game logos as custom emojis.

    python upload_emojis.py [carpeta]      # default: local/emojis

Every <name>.png in the folder is uploaded twice:
  - as an application emoji (Dev Portal → Emojis) — what post_messages.py puts
    on the buttons, since the bot can always use its own emojis;
  - as a server emoji, so members can use it in chat too.

Emojis that already exist (by name) are skipped, so it's safe to re-run. The
logos live in local/ because they're third-party trademarks and the repo is
public.
"""

import base64
import os
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

DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local", "emojis")


def api(method, path, body=None):
    """Returns (payload, error_string). Mirrors the helper in post_messages.py."""
    res = requests.request(method, API + path, headers=HEADERS, json=body, timeout=30)
    if not res.ok:
        return None, f"HTTP {res.status_code}: {res.text}"
    if res.status_code == 204 or not res.content:
        return {}, None
    return res.json(), None


def data_uri(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def upload(label, create_path, existing_names, name, image):
    if name in existing_names:
        print(f"  ↩ {label}: '{name}' ya existe (ID: {existing_names[name]})")
        return
    emoji, err = api("POST", create_path, {"name": name, "image": image})
    if err:
        print(f"  ✗ {label}: '{name}': {err}")
    else:
        print(f"  ✓ {label}: '{name}' subido (ID: {emoji['id']})")


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    files = sorted(f for f in os.listdir(folder) if f.endswith(".png"))
    if not files:
        sys.exit(f"✗ No hay PNGs en {folder}")

    app, err = api("GET", "/applications/@me")
    if err:
        sys.exit(f"✗ No se pudo leer la aplicación: {err}")
    app_path = f"/applications/{app['id']}/emojis"

    app_emojis, err = api("GET", app_path)
    if err:
        sys.exit(f"✗ No se pudieron listar los emojis de la app: {err}")
    guild_emojis, err = api("GET", f"/guilds/{GUILD_ID}/emojis")
    if err:
        sys.exit(f"✗ No se pudieron listar los emojis del servidor: {err}")

    app_names = {e["name"]: e["id"] for e in app_emojis["items"]}
    guild_names = {e["name"]: e["id"] for e in guild_emojis}
    guild_path = f"/guilds/{GUILD_ID}/emojis"

    for filename in files:
        name = filename[:-len(".png")]
        image = data_uri(os.path.join(folder, filename))
        upload("app", app_path, app_names, name, image)
        upload("servidor", guild_path, guild_names, name, image)


if __name__ == "__main__":
    main()
