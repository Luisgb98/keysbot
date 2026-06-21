import urllib.request
import urllib.error
import json
import os

TOKEN    = os.environ["DISCORD_TOKEN"]
GUILD_ID = os.environ["GUILD_ID"]

TECH_ID   = os.environ["ROLE_TECH"]
DIABLO_ID = os.environ["ROLE_DIABLO"]
POE_ID    = os.environ["ROLE_POE"]

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs, 10)",
    "Content-Type": "application/json",
}

def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"https://discord.com/api/v10{path}",
        data=data, headers=HEADERS, method=method
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()}"

# 1. Fetch all roles and find Tech
roles, err = api("GET", f"/guilds/{GUILD_ID}/roles")
if err:
    print(f"Failed to fetch roles: {err}"); exit(1)

tech = next((r for r in roles if r["id"] == TECH_ID), None)
if not tech:
    print("Tech role not found"); exit(1)

print(f"Tech permissions: {tech['permissions']}")

# 2. Copy permissions to Diablo and POE
for role_id, name in [(DIABLO_ID, "Diablo"), (POE_ID, "POE")]:
    result, err = api("PATCH", f"/guilds/{GUILD_ID}/roles/{role_id}", {"permissions": tech["permissions"]})
    if err:
        print(f"  Failed to update {name}: {err}")
    else:
        print(f"  {name} updated — permissions now: {result['permissions']}")
