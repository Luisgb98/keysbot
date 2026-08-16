/**
 * keysbot — Discord button roles on Cloudflare Workers.
 *
 * Discord POSTs every button click here as a signed webhook, so the whole bot
 * is one stateless HTTP handler: verify the Ed25519 signature, toggle the role,
 * answer with an ephemeral message. No gateway, no persistent process.
 *
 * Config:
 *   secrets — DISCORD_TOKEN, DISCORD_PUBLIC_KEY
 *   vars    — GUILD_ID, ALLOWED_ROLE_IDS (comma-separated), LOG_CHANNEL_ID (optional)
 */

const API = "https://discord.com/api/v10";

// Interaction types
const PING = 1;
const MESSAGE_COMPONENT = 3;

// Interaction callback types
const PONG = 1;
const CHANNEL_MESSAGE_WITH_SOURCE = 4;

const EPHEMERAL = 64;

// ── Signature verification ────────────────────────────────────────────────────

function hexToBytes(hex) {
  if (hex.length % 2 !== 0 || /[^0-9a-fA-F]/.test(hex)) return null;
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return bytes;
}

async function importPublicKey(publicKeyHex) {
  const raw = hexToBytes(publicKeyHex);
  if (!raw) throw new Error("DISCORD_PUBLIC_KEY is not valid hex");
  // Newer workerd exposes the standardised "Ed25519" algorithm; older runtimes
  // only know Cloudflare's "NODE-ED25519" spelling.
  try {
    return await crypto.subtle.importKey("raw", raw, { name: "Ed25519" }, false, ["verify"]);
  } catch {
    return await crypto.subtle.importKey(
      "raw", raw, { name: "NODE-ED25519", namedCurve: "NODE-ED25519" }, false, ["verify"],
    );
  }
}

/** Returns the raw body if the signature checks out, otherwise null. */
async function verifyRequest(request, publicKeyHex) {
  const signature = request.headers.get("X-Signature-Ed25519");
  const timestamp = request.headers.get("X-Signature-Timestamp");
  if (!signature || !timestamp) return null;

  const sigBytes = hexToBytes(signature);
  if (!sigBytes || sigBytes.length !== 64) return null;

  const body = await request.text();
  const key = await importPublicKey(publicKeyHex);
  const message = new TextEncoder().encode(timestamp + body);

  let ok;
  try {
    ok = await crypto.subtle.verify(key.algorithm.name, key, sigBytes, message);
  } catch {
    return null;
  }
  return ok ? body : null;
}

// ── Discord REST ──────────────────────────────────────────────────────────────

async function discord(env, method, path, body) {
  const res = await fetch(API + path, {
    method,
    headers: {
      Authorization: `Bot ${env.DISCORD_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs, 10)",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Discord ${method} ${path} → ${res.status}: ${await res.text()}`);
  }
  return res;
}

/** Best-effort log line to #keysbot; never fails the interaction. */
async function log(env, text) {
  console.log(text);
  if (!env.LOG_CHANNEL_ID) return;
  try {
    await discord(env, "POST", `/channels/${env.LOG_CHANNEL_ID}/messages`, {
      content: text,
      allowed_mentions: { parse: [] },
    });
  } catch (err) {
    console.error(`no se pudo escribir en el canal de logs: ${err.message}`);
  }
}

// ── Responses ─────────────────────────────────────────────────────────────────

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function ephemeral(content) {
  return json({
    type: CHANNEL_MESSAGE_WITH_SOURCE,
    data: { content, flags: EPHEMERAL, allowed_mentions: { parse: [] } },
  });
}

// ── Button handling ───────────────────────────────────────────────────────────

function allowedRoleIds(env) {
  return new Set(
    (env.ALLOWED_ROLE_IDS || "").split(",").map((s) => s.trim()).filter(Boolean),
  );
}

/**
 * The clicked button's label, dug out of the message that came with the
 * interaction — saves a round-trip to fetch the role's name.
 */
function labelFor(message, customId) {
  for (const row of message?.components || []) {
    for (const component of row.components || []) {
      if (component.custom_id === customId) return component.label || customId;
    }
  }
  return customId;
}

async function handleButton(interaction, env) {
  const customId = interaction.data?.custom_id || "";
  if (!customId.startsWith("role:")) {
    return ephemeral("❌ Botón no reconocido.");
  }
  const roleId = customId.slice("role:".length);

  if (env.GUILD_ID && interaction.guild_id !== env.GUILD_ID) {
    return ephemeral("❌ Este botón solo funciona en el servidor configurado.");
  }
  if (!allowedRoleIds(env).has(roleId)) {
    console.warn(`rol no permitido: ${roleId}`);
    return ephemeral("❌ Ese rol no está disponible.");
  }

  const member = interaction.member;
  const userId = member?.user?.id;
  if (!userId) return ephemeral("❌ No se pudo identificar al miembro.");

  const label = labelFor(interaction.message, customId);
  const hasRole = (member.roles || []).includes(roleId);
  const path = `/guilds/${interaction.guild_id}/members/${userId}/roles/${roleId}`;

  try {
    await discord(env, hasRole ? "DELETE" : "PUT", path);
  } catch (err) {
    console.error(err.message);
    return ephemeral(`❌ No se pudo actualizar el rol **${label}**. Avisa a un administrador.`);
  }

  const name = member.nick || member.user.global_name || member.user.username;
  return {
    response: ephemeral(hasRole ? `➖ Rol **${label}** quitado` : `✅ Rol **${label}** añadido`),
    logLine: hasRole ? `➖ ${name} ← **${label}**` : `✅ ${name} → **${label}**`,
  };
}

// ── Entrypoint ────────────────────────────────────────────────────────────────

export default {
  async fetch(request, env, ctx) {
    if (request.method === "GET") {
      return new Response("keysbot: endpoint de interacciones activo", {
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    }
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }
    if (!env.DISCORD_PUBLIC_KEY) {
      console.error("DISCORD_PUBLIC_KEY no configurado");
      return new Response("Server misconfigured", { status: 500 });
    }

    const body = await verifyRequest(request, env.DISCORD_PUBLIC_KEY);
    if (body === null) {
      return new Response("invalid request signature", { status: 401 });
    }

    let interaction;
    try {
      interaction = JSON.parse(body);
    } catch {
      return new Response("Bad request", { status: 400 });
    }

    if (interaction.type === PING) {
      return json({ type: PONG });
    }

    if (interaction.type === MESSAGE_COMPONENT) {
      const result = await handleButton(interaction, env);
      if (result instanceof Response) return result;
      // Logging happens after the reply is on its way — Discord's 3s budget is tight.
      ctx.waitUntil(log(env, result.logLine));
      return result.response;
    }

    return ephemeral("❓ Interacción no soportada.");
  },
};
