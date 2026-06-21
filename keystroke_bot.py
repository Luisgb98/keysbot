import discord
import asyncio
import json
import os

TOKEN    = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])

# ── Role IDs ──────────────────────────────────────────────────────────────────
ROLES = {
    "💻": int(os.environ["ROLE_TECH"]),
    "🎮": int(os.environ["ROLE_GAMING"]),
    "🎌": int(os.environ["ROLE_ANIME"]),
    "⚡": int(os.environ["ROLE_POE"]),
    "🔥": int(os.environ["ROLE_DIABLO"]),
}

# ── Messages to post ───────────────────────────────────────────────────────────
MESSAGES = {
    "msg1": {
        "emojis": ["💻", "🎮", "🎌"],
        "text": (
            "🎭 **Elige tu comunidad de interés**\n\n"
            "💻 ─ **Tech** · Tecnología y programación\n"
            "🎮 ─ **Gaming** · Videojuegos en general\n"
            "🎌 ─ **Anime** · Series y manga\n\n"
            "*Reacciona para obtener el rol. Quita la reacción para perderlo.*"
        ),
    },
    "msg2": {
        "emojis": ["⚡", "🔥"],
        "text": (
            "⚔️ **Elige tu juego**\n\n"
            "⚡ ─ **Path of Exile** · Accede a los canales de POE\n"
            "🔥 ─ **Diablo** · Accede a los canales de Diablo\n\n"
            "*Reacciona para obtener el rol. Quita la reacción para perderlo.*"
        ),
    },
}

STATE_FILE = os.path.join(os.path.dirname(__file__), "bot_state.json")

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True  # requires Server Members Intent in Dev Portal

client = discord.Client(intents=intents)
tracked = {}  # message_id (int) -> {emoji: role_id}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


@client.event
async def on_ready():
    print(f"✓ Conectado como {client.user}")
    guild = client.get_guild(GUILD_ID)

    channel = discord.utils.get(guild.text_channels, name="elige-tu-rol")
    if not channel:
        print("✗ Canal 'elige-tu-rol' no encontrado. Créalo primero.")
        return

    state = load_state()

    for key, msg_def in MESSAGES.items():
        msg = None
        saved_id = state.get(key)

        if saved_id:
            try:
                msg = await channel.fetch_message(int(saved_id))
                print(f"  ↩ Mensaje '{key}' ya existe (ID: {msg.id})")
            except discord.NotFound:
                msg = None

        if msg is None:
            msg = await channel.send(msg_def["text"])
            for emoji in msg_def["emojis"]:
                await msg.add_reaction(emoji)
            state[key] = str(msg.id)
            save_state(state)
            print(f"  ✓ Mensaje '{key}' publicado (ID: {msg.id})")

        tracked[msg.id] = {e: ROLES[e] for e in msg_def["emojis"]}

    print("✓ Bot listo — escuchando reacciones\n")


async def apply_reaction(payload, add: bool):
    if payload.guild_id != GUILD_ID:
        return
    if payload.user_id == client.user.id:
        return
    if payload.message_id not in tracked:
        return

    emoji = str(payload.emoji)
    role_id = tracked[payload.message_id].get(emoji)
    if not role_id:
        return

    guild  = client.get_guild(payload.guild_id)
    role   = guild.get_role(role_id)
    member = guild.get_member(payload.user_id)

    if not role or not member:
        return

    if add:
        await member.add_roles(role, reason="Reaction role")
        print(f"  + {member.display_name} → {role.name}")
    else:
        await member.remove_roles(role, reason="Reaction role")
        print(f"  - {member.display_name} ← {role.name}")


@client.event
async def on_raw_reaction_add(payload):
    await apply_reaction(payload, add=True)


@client.event
async def on_raw_reaction_remove(payload):
    await apply_reaction(payload, add=False)


client.run(TOKEN)
