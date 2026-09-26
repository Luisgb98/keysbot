"""One-shot script: create the AION 2 / WoW Forever roles.

    python setup_roles.py

Finds each role by name and creates it only if it's missing, so it's safe to
re-run. Both are button roles: members toggle them from #elige-tu-rol.

New roles get the Tech role's permissions (same thing fetch_roles.py did for
POE/Diablo). Prints the lines to paste into .env and the new ALLOWED_ROLE_IDS.
"""

import os
import sys

import requests

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = os.environ["GUILD_ID"]
TECH_ID = os.environ["ROLE_TECH"]

API = "https://discord.com/api/v10"
HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs, 10)",
    "Content-Type": "application/json",
}

# (env var, role name, colour, hoist)
NEW_ROLES = [
    ("ROLE_AION2", "AION 2", 0x4FA3E0, False),
    ("ROLE_WOW", "WoW Forever", 0xF0B232, False),
]


def api(method, path, body=None):
    """Returns (payload, error_string). Mirrors the helper in post_messages.py."""
    res = requests.request(method, API + path, headers=HEADERS, json=body, timeout=30)
    if not res.ok:
        return None, f"HTTP {res.status_code}: {res.text}"
    if res.status_code == 204 or not res.content:
        return {}, None
    return res.json(), None


def main():
    roles, err = api("GET", f"/guilds/{GUILD_ID}/roles")
    if err:
        sys.exit(f"✗ No se pudieron listar los roles: {err}")

    tech = next((r for r in roles if r["id"] == TECH_ID), None)
    if not tech:
        sys.exit("✗ Rol Tech no encontrado (revisa ROLE_TECH)")

    by_name = {r["name"]: r for r in roles}
    ids = {}
    for env_var, name, color, hoist in NEW_ROLES:
        role = by_name.get(name)
        if role:
            print(f"  ↩ Rol '{name}' ya existe (ID: {role['id']})")
        else:
            role, err = api("POST", f"/guilds/{GUILD_ID}/roles", {
                "name": name,
                "permissions": tech["permissions"],
                "color": color,
                "hoist": hoist,
                "mentionable": True,
            })
            if err:
                sys.exit(f"✗ No se pudo crear '{name}': {err}")
            print(f"  ✓ Rol '{name}' creado (ID: {role['id']})")
        ids[env_var] = role["id"]

    print("\nAñade esto a .env:")
    for env_var, role_id in ids.items():
        print(f"  {env_var}={role_id}")

    print("\nY añádelos a ALLOWED_ROLE_IDS en worker/wrangler.toml:")
    print(f"  ,{ids['ROLE_AION2']},{ids['ROLE_WOW']}")


if __name__ == "__main__":
    main()
