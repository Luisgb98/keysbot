import urllib.request
import urllib.error
import json
import time
import os

TOKEN    = os.environ["DISCORD_TOKEN"]
GUILD_ID = os.environ["GUILD_ID"]

# Role IDs
EVERYONE   = GUILD_ID
JEFE       = os.environ["ROLE_JEFE"]
MODERADOR  = os.environ["ROLE_MODERADOR"]
ROL_DIABLO = os.environ["ROLE_DIABLO"]
ROL_POE    = os.environ["ROLE_POE"]

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs, 10)",
    "Content-Type": "application/json",
}

VIEW = 1024  # VIEW_CHANNEL permission bit

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

def create_channel(name, parent_id, overwrites, channel_type=0):
    """type 0 = text, 4 = category"""
    body = {
        "name": name,
        "type": channel_type,
        "parent_id": parent_id,
        "permission_overwrites": overwrites,
    }
    result, err = api("POST", f"/guilds/{GUILD_ID}/channels", body)
    if err:
        print(f"  ✗ {name}: {err}")
    else:
        print(f"  ✓ #{name}")
    time.sleep(0.5)  # avoid rate limits
    return result

# Permission overwrites that restrict a channel/category to specific roles only
def restricted_to(allowed_role_ids):
    overwrites = [{"id": EVERYONE, "type": 0, "allow": "0", "deny": str(VIEW)}]
    for role_id in allowed_role_ids:
        overwrites.append({"id": role_id, "type": 0, "allow": str(VIEW), "deny": "0"})
    return overwrites

# --- Fetch current channels ---
print("Fetching current channels...")
channels, err = api("GET", f"/guilds/{GUILD_ID}/channels")
if err:
    print(f"Error: {err}"); exit(1)

categories = {c["name"].lower(): c for c in channels if c["type"] == 4}
print(f"Found categories: {[c['name'] for c in channels if c['type'] == 4]}\n")

# --- POE section ---
poe_allowed = [JEFE, MODERADOR, ROL_POE]
poe_overwrites = restricted_to(poe_allowed)

# Find or create POE category
poe_cat = categories.get("poe")
if poe_cat:
    print(f"Found existing POE category (ID: {poe_cat['id']}), updating permissions...")
    api("PATCH", f"/channels/{poe_cat['id']}", {"permission_overwrites": poe_overwrites})
    poe_cat_id = poe_cat["id"]
else:
    print("Creating POE category...")
    result = create_channel("POE", None, poe_overwrites, channel_type=4)
    poe_cat_id = result["id"] if result else None

if poe_cat_id:
    print("Creating POE channels...")
    existing_names = {c["name"] for c in channels if c.get("parent_id") == poe_cat_id}

    poe_channels = [
        "anuncios-poe",
        "general-poe",
        "guias",
        "filtros-de-loot",
        "construcciones",
        "economia-y-comercio",
        "mapas-y-endgame",
        # Clases POE 2
        "clase-bruja",
        "clase-hechicera",
        "clase-guerrero",
        "clase-monje",
        "clase-mercenario",
        "clase-cazadora",
    ]
    for ch in poe_channels:
        if ch not in existing_names:
            create_channel(ch, poe_cat_id, poe_overwrites)
        else:
            print(f"  ~ #{ch} ya existe, omitiendo")

# --- Diablo section ---
diablo_allowed = [JEFE, MODERADOR, ROL_DIABLO]
diablo_overwrites = restricted_to(diablo_allowed)

# Find or create Diablo category
diablo_cat = categories.get("diablo")
if diablo_cat:
    print(f"\nFound existing Diablo category (ID: {diablo_cat['id']}), updating permissions...")
    api("PATCH", f"/channels/{diablo_cat['id']}", {"permission_overwrites": diablo_overwrites})
    diablo_cat_id = diablo_cat["id"]
else:
    print("\nCreating Diablo category...")
    result = create_channel("Diablo", None, diablo_overwrites, channel_type=4)
    diablo_cat_id = result["id"] if result else None

if diablo_cat_id:
    print("Creating Diablo channels...")
    existing_names = {c["name"] for c in channels if c.get("parent_id") == diablo_cat_id}

    diablo_channels = [
        "anuncios-diablo",
        "general-diablo",
        "guias",
        "construcciones",
        "temporada-actual",
        "economia-y-comercio",
        "mazmorras-y-endgame",
        # Clases Diablo 4
        "clase-barbaro",
        "clase-druida",
        "clase-hechicero",
        "clase-nigromante",
        "clase-picaro",
        "clase-espiritualista",
    ]
    for ch in diablo_channels:
        if ch not in existing_names:
            create_channel(ch, diablo_cat_id, diablo_overwrites)
        else:
            print(f"  ~ #{ch} ya existe, omitiendo")

print("\nDone!")
