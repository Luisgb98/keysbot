/**
 * Twitch EventSub → "#directos".
 *
 * Twitch POSTs a signed webhook to /twitch when the channel goes live
 * (subscription created once with subscribe_twitch.py). We verify the HMAC,
 * answer the one-off verification challenge, and on stream.online post an
 * announcement pinging the Twitch role.
 *
 * Config:
 *   secrets — TWITCH_EVENTSUB_SECRET, TWITCH_CLIENT_SECRET
 *   vars    — TWITCH_CLIENT_ID, TWITCH_BROADCASTER_ID, LIVE_CHANNEL_ID,
 *             ROLE_TWITCH_ID, LIVE_COOLDOWN_MINUTES (optional, default 120)
 */

import { appEmojis, discord, log, recentMessages } from "./discord.js";
import { hmacSha256Hex, isFresh, safeEqual } from "./hmac.js";

// Twitch drops messages older than 10 minutes as replays; so do we.
const MAX_AGE_SECONDS = 10 * 60;
const DEFAULT_COOLDOWN_MINUTES = 120;

async function verifyTwitch(request, secret) {
  const id = request.headers.get("Twitch-Eventsub-Message-Id");
  const timestamp = request.headers.get("Twitch-Eventsub-Message-Timestamp");
  const signature = request.headers.get("Twitch-Eventsub-Message-Signature");
  if (!id || !timestamp || !signature) return null;
  if (!isFresh(timestamp, MAX_AGE_SECONDS)) return null;

  const body = await request.text();
  const expected = "sha256=" + (await hmacSha256Hex(secret, id + timestamp + body));
  return safeEqual(expected, signature) ? body : null;
}

/** The channel's current title and game — /channels always answers, /streams can lag. */
async function channelInfo(env, broadcasterId) {
  try {
    const tokenRes = await fetch("https://id.twitch.tv/oauth2/token", {
      method: "POST",
      body: new URLSearchParams({
        client_id: env.TWITCH_CLIENT_ID,
        client_secret: env.TWITCH_CLIENT_SECRET,
        grant_type: "client_credentials",
      }),
    });
    if (!tokenRes.ok) throw new Error(`token → ${tokenRes.status}`);
    const { access_token } = await tokenRes.json();

    const res = await fetch(`https://api.twitch.tv/helix/channels?broadcaster_id=${broadcasterId}`, {
      headers: { "Client-Id": env.TWITCH_CLIENT_ID, Authorization: `Bearer ${access_token}` },
    });
    if (!res.ok) throw new Error(`helix/channels → ${res.status}`);
    const { data } = await res.json();
    return data?.[0] ?? {};
  } catch (err) {
    // The announcement goes out without a title rather than not at all.
    console.error(`no se pudo leer el canal de Twitch: ${err.message}`);
    return {};
  }
}

/**
 * A reconnect after a dropped stream fires stream.online again. If the bot
 * already announced within the cooldown, stay quiet.
 */
async function announcedRecently(env) {
  const minutes = Number(env.LIVE_COOLDOWN_MINUTES) || DEFAULT_COOLDOWN_MINUTES;
  const [last] = await recentMessages(env, env.LIVE_CHANNEL_ID, 1);
  if (!last) return false;
  return Date.now() - Date.parse(last.timestamp) < minutes * 60 * 1000;
}

export function liveMessage({ roleId, login, name, title, game, emoji }) {
  const lines = [`${emoji ? emoji + " " : ""}<@&${roleId}> **¡${name} está en directo!**`];
  if (title) lines.push(`**${title}**`);
  if (game) lines.push(`🎮 ${game}`);
  lines.push(`https://twitch.tv/${login}`);
  return lines.join("\n");
}

async function announceLive(env, event) {
  if (await announcedRecently(env)) {
    console.log(`directo de ${event.broadcaster_user_login} ya anunciado hace poco, omitido`);
    return;
  }
  const [info, emojis] = await Promise.all([
    channelInfo(env, event.broadcaster_user_id),
    appEmojis(env),
  ]);
  await discord(env, "POST", `/channels/${env.LIVE_CHANNEL_ID}/messages`, {
    content: liveMessage({
      roleId: env.ROLE_TWITCH_ID,
      login: event.broadcaster_user_login,
      name: event.broadcaster_user_name,
      title: info.title,
      game: info.game_name,
      emoji: emojis.twitch,
    }),
    allowed_mentions: { roles: [env.ROLE_TWITCH_ID] },
  });
  await log(env, `🔴 Directo anunciado en <#${env.LIVE_CHANNEL_ID}>`);
}

export async function handleTwitch(request, env, ctx) {
  if (!env.TWITCH_EVENTSUB_SECRET) {
    console.error("TWITCH_EVENTSUB_SECRET no configurado");
    return new Response("Server misconfigured", { status: 500 });
  }
  const body = await verifyTwitch(request, env.TWITCH_EVENTSUB_SECRET);
  if (body === null) {
    return new Response("invalid request signature", { status: 401 });
  }

  let message;
  try {
    message = JSON.parse(body);
  } catch {
    return new Response("Bad request", { status: 400 });
  }

  const type = request.headers.get("Twitch-Eventsub-Message-Type");
  if (type === "webhook_callback_verification") {
    return new Response(message.challenge, { headers: { "Content-Type": "text/plain" } });
  }
  if (type === "revocation") {
    ctx.waitUntil(log(env, `⚠️ Twitch revocó la suscripción ${message.subscription?.type}: ${message.subscription?.status}`));
    return new Response(null, { status: 204 });
  }
  if (type !== "notification") {
    return new Response(null, { status: 204 });
  }

  const event = message.event ?? {};
  const isOurLive =
    message.subscription?.type === "stream.online" &&
    event.type === "live" &&
    event.broadcaster_user_id === env.TWITCH_BROADCASTER_ID;
  if (isOurLive) {
    // Twitch wants its 2xx within a few seconds; the announcement can follow.
    ctx.waitUntil(
      announceLive(env, event).catch((err) => console.error(`anuncio de directo fallido: ${err.message}`)),
    );
  }
  return new Response(null, { status: 204 });
}
