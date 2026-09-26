/**
 * keystroke-hub → "#videos".
 *
 * The hub POSTs to /videos when a video is marked Published (or its
 * "Anunciar en Discord" button is pressed). The request is signed with a
 * shared secret; the body carries the title and the video's links:
 *
 *   POST /videos
 *   X-Keysbot-Timestamp: <unix seconds>
 *   X-Keysbot-Signature: sha256=<hex HMAC-SHA256(secret, timestamp + "." + body)>
 *
 *   { "id": "<idea uuid>", "title": "…",
 *     "links": { "youtube": "https://…", "tiktok": "https://…", "instagram": "https://…" } }
 *
 * Answers:
 *   201 { status: "announced", messageId }         — posted now
 *   200 { status: "already-announced", messageId } — one of its links is already
 *                                                     in #videos; safe to retry
 *   401 bad signature · 400 bad JSON · 422 { error, issues } · 502 Discord failed
 *
 * Config:
 *   secrets — VIDEOS_HMAC_SECRET
 *   vars    — VIDEOS_CHANNEL_ID, ROLE_VIDEOS_ID
 */

import { appEmojis, discord, log, recentMessages } from "./discord.js";
import { hmacSha256Hex, isFresh, safeEqual } from "./hmac.js";

const MAX_AGE_SECONDS = 5 * 60;
// How far back #videos is searched for a repeat.
const DEDUPE_WINDOW = 50;
const MAX_TITLE = 200;

// In announcement order; the first link present gets Discord's preview.
const PLATFORMS = {
  youtube: { label: "YouTube", hosts: ["youtube.com", "youtu.be"] },
  tiktok: { label: "TikTok", hosts: ["tiktok.com"] },
  instagram: { label: "Instagram", hosts: ["instagram.com"] },
};

function json(data, status) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function verifyHub(request, secret) {
  const timestamp = request.headers.get("X-Keysbot-Timestamp");
  const signature = request.headers.get("X-Keysbot-Signature");
  if (!timestamp || !signature || !isFresh(timestamp, MAX_AGE_SECONDS)) return null;

  const body = await request.text();
  const expected = "sha256=" + (await hmacSha256Hex(secret, `${timestamp}.${body}`));
  return safeEqual(expected, signature) ? body : null;
}

function hostMatches(url, hosts) {
  const host = url.hostname.replace(/^(www|m|vm)\./, "");
  return hosts.includes(host);
}

/** Returns { video } or { issues } — every problem at once, like keystroke.es. */
export function parseVideo(payload) {
  const issues = [];
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return { issues: ["el cuerpo debe ser un objeto JSON"] };
  }

  const { id, title, links } = payload;
  if (typeof id !== "string" || !id.trim()) issues.push("id: obligatorio");
  if (typeof title !== "string" || !title.trim()) issues.push("title: obligatorio");
  else if (title.trim().length > MAX_TITLE) issues.push(`title: máximo ${MAX_TITLE} caracteres`);

  const clean = {};
  if (typeof links !== "object" || links === null || Array.isArray(links)) {
    issues.push("links: obligatorio");
  } else {
    for (const [platform, value] of Object.entries(links)) {
      const spec = PLATFORMS[platform];
      if (!spec) {
        issues.push(`links.${platform}: plataforma no soportada`);
        continue;
      }
      if (value === null || value === undefined || value === "") continue;
      let url;
      try {
        url = new URL(value);
      } catch {
        issues.push(`links.${platform}: no es una URL`);
        continue;
      }
      if (url.protocol !== "https:" || !hostMatches(url, spec.hosts)) {
        issues.push(`links.${platform}: debe ser un enlace https de ${spec.label}`);
        continue;
      }
      clean[platform] = url.toString();
    }
    if (!issues.some((i) => i.startsWith("links")) && Object.keys(clean).length === 0) {
      issues.push("links: hace falta al menos un enlace");
    }
  }

  if (issues.length) return { issues };
  return { video: { id: id.trim(), title: title.trim(), links: clean } };
}

export function videoMessage({ roleId, title, links, emojis }) {
  const lines = [`${emojis.youtube ? emojis.youtube + " " : ""}<@&${roleId}> **¡Nuevo vídeo!**`, `**${title}**`, ""];
  let previewed = false;
  for (const [platform, { label }] of Object.entries(PLATFORMS)) {
    const url = links[platform];
    if (!url) continue;
    // Only the first link unfurls; the rest would stack more previews.
    const shown = previewed ? `<${url}>` : url;
    previewed = true;
    lines.push(`${emojis[platform] ? emojis[platform] + " " : ""}${label}: ${shown}`);
  }
  return lines.join("\n");
}

export async function handleVideo(request, env) {
  if (!env.VIDEOS_HMAC_SECRET) {
    console.error("VIDEOS_HMAC_SECRET no configurado");
    return json({ error: "server-misconfigured" }, 500);
  }
  const body = await verifyHub(request, env.VIDEOS_HMAC_SECRET);
  if (body === null) return json({ error: "invalid-signature" }, 401);

  let payload;
  try {
    payload = JSON.parse(body);
  } catch {
    return json({ error: "invalid-json" }, 400);
  }
  const { video, issues } = parseVideo(payload);
  if (issues) return json({ error: "validation", issues }, 422);

  try {
    // Idempotency without storage: a retry finds its own links in #videos.
    const urls = Object.values(video.links);
    const recent = await recentMessages(env, env.VIDEOS_CHANNEL_ID, DEDUPE_WINDOW);
    const previous = recent.find((m) => urls.some((url) => m.content?.includes(url)));
    if (previous) {
      return json({ status: "already-announced", messageId: previous.id }, 200);
    }

    const emojis = await appEmojis(env);
    const res = await discord(env, "POST", `/channels/${env.VIDEOS_CHANNEL_ID}/messages`, {
      content: videoMessage({ roleId: env.ROLE_VIDEOS_ID, ...video, emojis }),
      allowed_mentions: { roles: [env.ROLE_VIDEOS_ID] },
    });
    const message = await res.json();
    await log(env, `🎬 Vídeo anunciado en <#${env.VIDEOS_CHANNEL_ID}>: **${video.title}**`);
    return json({ status: "announced", messageId: message.id }, 201);
  } catch (err) {
    console.error(`anuncio de vídeo fallido: ${err.message}`);
    return json({ error: "discord-unavailable" }, 502);
  }
}
