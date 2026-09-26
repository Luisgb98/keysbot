import urllib.request
import urllib.error
import json
import time
import os
import re

TOKEN    = os.environ["DISCORD_TOKEN"]
GUILD_ID = os.environ["GUILD_ID"]

# Role IDs
EVERYONE   = GUILD_ID
JEFE       = os.environ["ROLE_JEFE"]
MODERADOR  = os.environ["ROLE_MODERADOR"]
ROL_DIABLO = os.environ["ROLE_DIABLO"]
ROL_POE    = os.environ["ROLE_POE"]
ROL_AION2  = os.environ["ROLE_AION2"]
ROL_WOW    = os.environ["ROLE_WOW"]

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

FORUM_TOPIC = "Un hilo por clase. Usa la etiqueta de tu clase al publicar."

def create_channel(name, parent_id, overwrites, channel_type=0, extra=None):
    """type 0 = text, 2 = voice, 4 = category, 15 = forum"""
    body = {
        "name": name,
        "type": channel_type,
        "parent_id": parent_id,
        "permission_overwrites": overwrites,
        **(extra or {}),
    }
    result, err = api("POST", f"/guilds/{GUILD_ID}/channels", body)
    if err:
        print(f"  ✗ {name}: {err}")
    else:
        icon = {2: "🔊 ", 15: "💬 "}.get(channel_type, "#")
        print(f"  ✓ {icon}{name}")
    time.sleep(0.5)  # avoid rate limits
    return result

# Permission overwrites that restrict a channel/category to specific roles only
def restricted_to(allowed_role_ids):
    overwrites = [{"id": EVERYONE, "type": 0, "allow": "0", "deny": str(VIEW)}]
    for role_id in allowed_role_ids:
        overwrites.append({"id": role_id, "type": 0, "allow": str(VIEW), "deny": "0"})
    return overwrites

def base_name(name):
    """'⚡ POE' → 'poe': categories carry an emoji prefix on the server."""
    return re.sub(r"^\W+", "", name).strip().lower()

def forum(name, tags, emoji):
    """A forum channel like poe-clases: one thread per class, tagged. `emoji`
    is the server emoji (from upload_emojis.py) used as default reaction."""
    return {
        "name": name,
        "topic": FORUM_TOPIC,
        "available_tags": [{"name": t} for t in tags],
        "emoji": emoji,
    }

def reaction_for(emoji_name):
    """The game's logo if it's uploaded to the server, 🔥 otherwise."""
    if emoji_name in guild_emojis:
        return {"emoji_id": guild_emojis[emoji_name]}
    print(f"  ! Emoji '{emoji_name}' no está en el servidor, se usa 🔥")
    return {"emoji_name": "🔥"}

# --- Sections ---
# Each category is locked to Jefe + Moderador + its own role. Channels are text
# unless listed under "voice"; "forum" is the per-class forum (one thread per
# class, one tag per class). POE and Diablo mirror what's live on the server.
SECTIONS = [
    {
        "category": "⚡ POE",
        "role": ROL_POE,
        "channels": [
            "anuncios-poe",
            "general-poe",
            "guias",
            "construcciones",
            "filtros-de-loot",
            "economia-y-comercio",
            "mapas-y-endgame",
        ],
        "forum": forum("poe-clases", [
            "Bruja", "Hechicera", "Guerrero", "Monje", "Mercenario", "Cazadora",
        ], "poe"),
    },
    {
        "category": "🔥 Diablo",
        "role": ROL_DIABLO,
        "channels": [
            "anuncios-diablo",
            "general-diablo",
            "guias",
            "construcciones",
            "temporada-actual",
            "economia-y-comercio",
            "mazmorras-y-endgame",
        ],
        "forum": forum("diablo-clases", [
            "Barbaro", "Druida", "Hechicero", "Nigromante", "Picaro", "Espiritualista",
        ], "diablo"),
    },
    {
        "category": "✨ AION 2",
        "role": ROL_AION2,
        "channels": [
            # Lo que sale en el canal: noticias, guías, builds y experimentos
            "noticias-aion2",
            "general-aion2",
            "guias",
            "experimentos",
            "economia-y-comercio",
            "mazmorras-y-endgame",
            "pvp-y-abismo",
            # Guild Spells of Keystroke
            "spells-of-keystroke",
        ],
        # Las 8 clases de lanzamiento global
        "forum": forum("aion2-clases", [
            "Gladiador", "Templario", "Asesino", "Arquero",
            "Hechicero", "Invocador", "Clerigo", "Cantor",
        ], "aion2"),
        "voice": ["Spells of Keystroke"],
    },
    {
        "category": "🐉 WoW Forever",
        "role": ROL_WOW,
        "channels": [
            # Lo que sale en el canal: noticias, guías, builds y experimentos
            "noticias-wow",
            "general-wow",
            "guias",
            "experimentos",
            "subasta-y-economia",
            "profesiones",
            "mazmorras-y-raids",
            "pvp",
        ],
        "forum": forum("wow-clases", [
            "Guerrero", "Paladin", "Cazador", "Picaro", "Sacerdote",
            "Chaman", "Mago", "Brujo", "Druida",
        ], "wowforever"),
    },
]

# --- Fetch current channels ---
print("Fetching current channels...")
channels, err = api("GET", f"/guilds/{GUILD_ID}/channels")
if err:
    print(f"Error: {err}"); exit(1)

categories = {base_name(c["name"]): c for c in channels if c["type"] == 4}

emojis, err = api("GET", f"/guilds/{GUILD_ID}/emojis")
if err:
    print(f"Error: {err}"); exit(1)
guild_emojis = {e["name"]: e["id"] for e in emojis}
print(f"Found categories: {[c['name'] for c in channels if c['type'] == 4]}")

for section in SECTIONS:
    name = section["category"]
    overwrites = restricted_to([JEFE, MODERADOR, section["role"]])

    # Find or create the category
    cat = categories.get(base_name(name))
    if cat:
        print(f"\nFound existing {name} category (ID: {cat['id']}), updating permissions...")
        api("PATCH", f"/channels/{cat['id']}", {"permission_overwrites": overwrites})
        cat_id = cat["id"]
    else:
        print(f"\nCreating {name} category...")
        result = create_channel(name, None, overwrites, channel_type=4)
        cat_id = result["id"] if result else None

    if not cat_id:
        continue

    print(f"Creating {name} channels...")
    existing_names = {c["name"] for c in channels if c.get("parent_id") == cat_id}
    wanted = [(ch, 0, None) for ch in section["channels"]]
    if "forum" in section:
        spec = dict(section["forum"])
        spec["default_reaction_emoji"] = reaction_for(spec.pop("emoji"))
        wanted.append((spec["name"], 15, spec))
    wanted += [(ch, 2, None) for ch in section.get("voice", [])]
    for ch, ch_type, extra in wanted:
        if ch not in existing_names:
            create_channel(ch, cat_id, overwrites, channel_type=ch_type, extra=extra)
        else:
            print(f"  ~ {ch} ya existe, omitiendo")

print("\nDone!")
