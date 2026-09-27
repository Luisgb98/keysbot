import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";

import worker from "../src/index.js";
import { hmacSha256Hex } from "../src/hmac.js";
import { parseVideo, videoMessage } from "../src/videos.js";

const env = {
  DISCORD_TOKEN: "t".repeat(20),
  DISCORD_PUBLIC_KEY: "a".repeat(64),
  LOG_CHANNEL_ID: "",
  TWITCH_EVENTSUB_SECRET: "s".repeat(20),
  TWITCH_CLIENT_ID: "client",
  TWITCH_CLIENT_SECRET: "c".repeat(20),
  TWITCH_BROADCASTER_ID: "1234",
  LIVE_CHANNEL_ID: "900",
  ROLE_TWITCH_ID: "111",
  VIDEOS_HMAC_SECRET: "v".repeat(20),
  VIDEOS_CHANNEL_ID: "901",
  ROLE_VIDEOS_ID: "222",
};

// ── A fake Discord + Twitch behind global fetch ──────────────────────────────

let posted;         // messages POSTed to Discord channels
let channelHistory; // channelId → messages, newest first
let discordDown;

beforeEach(() => {
  posted = [];
  channelHistory = {};
  discordDown = false;
});

globalThis.fetch = async (input, init = {}) => {
  const url = new URL(typeof input === "string" ? input : input.url);
  const method = init.method ?? "GET";
  const ok = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

  if (url.hostname === "id.twitch.tv") return ok({ access_token: "tok" });
  if (url.hostname === "api.twitch.tv") {
    return ok({ data: [{ title: "Probando AION 2", game_name: "AION 2" }] });
  }

  if (discordDown) return new Response("boom", { status: 500 });
  const path = url.pathname.replace("/api/v10", "");
  if (path === "/applications/@me") return ok({ id: "app" });
  if (path === "/applications/app/emojis") {
    return ok({ items: [{ name: "twitch", id: "1" }, { name: "youtube", id: "2" }, { name: "tiktok", id: "3" }] });
  }
  const m = path.match(/^\/channels\/(\d+)\/messages$/);
  if (m && method === "GET") return ok(channelHistory[m[1]] ?? []);
  if (m && method === "POST") {
    const body = JSON.parse(init.body);
    posted.push({ channelId: m[1], ...body });
    return ok({ id: `msg${posted.length}` });
  }
  throw new Error(`fetch inesperado: ${method} ${url}`);
};

function ctx() {
  const pending = [];
  return { waitUntil: (p) => pending.push(p), settle: () => Promise.all(pending) };
}

// ── /videos ──────────────────────────────────────────────────────────────────

async function hubRequest(payload, { secret = env.VIDEOS_HMAC_SECRET, timestamp } = {}) {
  const body = JSON.stringify(payload);
  const ts = timestamp ?? String(Math.floor(Date.now() / 1000));
  const signature = "sha256=" + (await hmacSha256Hex(secret, `${ts}.${body}`));
  return new Request("https://keysbot.example/videos", {
    method: "POST",
    headers: { "X-Keysbot-Timestamp": ts, "X-Keysbot-Signature": signature },
    body,
  });
}

const video = {
  id: "idea-1",
  title: "Build de Gladiador para AION 2",
  links: {
    youtube: "https://www.youtube.com/watch?v=abc",
    tiktok: "https://www.tiktok.com/@keystrokeg/video/1",
  },
};

test("videos: announces with the role ping, the first link previewed", async () => {
  const res = await worker.fetch(await hubRequest(video), env, ctx());
  assert.equal(res.status, 201);
  assert.deepEqual(await res.json(), { status: "announced", messageId: "msg1" });

  const [msg] = posted;
  assert.equal(msg.channelId, "901");
  assert.deepEqual(msg.allowed_mentions, { roles: ["222"] });
  assert.match(msg.content, /<@&222> \*\*¡Nuevo vídeo!\*\*/);
  assert.match(msg.content, /\*\*Build de Gladiador para AION 2\*\*/);
  assert.match(msg.content, /<:youtube:2> YouTube: https:\/\/www\.youtube\.com\/watch\?v=abc/);
  assert.match(msg.content, /<:tiktok:3> TikTok: <https:\/\/www\.tiktok\.com\/@keystrokeg\/video\/1>/);
});

test("videos: a retry finds its link in #videos and doesn't post twice", async () => {
  channelHistory["901"] = [{ id: "old", content: "…YouTube: https://www.youtube.com/watch?v=abc" }];
  const res = await worker.fetch(await hubRequest(video), env, ctx());
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { status: "already-announced", messageId: "old" });
  assert.equal(posted.length, 0);
});

test("videos: wrong secret or stale timestamp is a 401", async () => {
  let res = await worker.fetch(await hubRequest(video, { secret: "x".repeat(20) }), env, ctx());
  assert.equal(res.status, 401);
  const stale = String(Math.floor(Date.now() / 1000) - 600);
  res = await worker.fetch(await hubRequest(video, { timestamp: stale }), env, ctx());
  assert.equal(res.status, 401);
  assert.equal(posted.length, 0);
});

test("videos: every validation problem comes back at once as a 422", async () => {
  const res = await worker.fetch(
    await hubRequest({ id: "", title: "", links: { youtube: "http://evil.example/x", kick: "https://kick.com/k" } }),
    env,
    ctx(),
  );
  assert.equal(res.status, 422);
  const { error, issues } = await res.json();
  assert.equal(error, "validation");
  assert.deepEqual(issues, [
    "id: obligatorio",
    "title: obligatorio",
    "links.youtube: debe ser un enlace https de YouTube",
    "links.kick: plataforma no soportada",
  ]);
});

test("videos: a Discord outage is a 502 the hub can retry", async () => {
  discordDown = true;
  const res = await worker.fetch(await hubRequest(video), env, ctx());
  assert.equal(res.status, 502);
});

test("parseVideo: short links and empty platforms", () => {
  const { video: v } = parseVideo({
    id: "x",
    title: " Hola ",
    links: { youtube: "https://youtu.be/abc", tiktok: "", instagram: null },
  });
  assert.deepEqual(v, { id: "x", title: "Hola", links: { youtube: "https://youtu.be/abc" } });
  assert.deepEqual(parseVideo({ id: "x", title: "t", links: {} }).issues, ["links: hace falta al menos un enlace"]);
});

test("videos: YouTube Shorts is announced, and share-link tracking is dropped", async () => {
  const res = await worker.fetch(
    await hubRequest({
      id: "idea-2",
      title: "AION 2: horarios del lanzamiento",
      links: {
        youtube_shorts: "https://youtube.com/shorts/xyz?si=abc",
        tiktok: "https://vm.tiktok.com/ZGdQ7bMg4/?_r=1",
        instagram: "https://www.instagram.com/reel/DdzCtesOC0g/?stkn=ZnZo",
      },
    }),
    env,
    ctx(),
  );
  assert.equal(res.status, 201);
  assert.equal(
    posted[0].content,
    "<:youtube:2> <@&222> **¡Nuevo vídeo!**\n**AION 2: horarios del lanzamiento**\n\n" +
      "<:youtube:2> YouTube Shorts: https://youtube.com/shorts/xyz?si=abc\n" +
      "<:tiktok:3> TikTok: <https://vm.tiktok.com/ZGdQ7bMg4/>\n" +
      "Instagram: <https://www.instagram.com/reel/DdzCtesOC0g/>",
  );
});

test("videos: a resend of an already-announced raw link is still a repeat", async () => {
  channelHistory["901"] = [{ id: "old", content: "Instagram: https://www.instagram.com/reel/DdzCtesOC0g/?stkn=ZnZo" }];
  const res = await worker.fetch(
    await hubRequest({ id: "idea-2", title: "T", links: { instagram: "https://www.instagram.com/reel/DdzCtesOC0g/?stkn=ZnZo" } }),
    env,
    ctx(),
  );
  assert.equal(res.status, 200);
  assert.equal(posted.length, 0);
});

test("videoMessage: works without emojis", () => {
  const text = videoMessage({ roleId: "9", title: "T", links: { instagram: "https://instagram.com/p/1" }, emojis: {} });
  assert.equal(text, "<@&9> **¡Nuevo vídeo!**\n**T**\n\nInstagram: https://instagram.com/p/1");
});

// ── /twitch ──────────────────────────────────────────────────────────────────

async function twitchRequest(type, payload, { secret = env.TWITCH_EVENTSUB_SECRET } = {}) {
  const body = JSON.stringify(payload);
  const id = crypto.randomUUID();
  const timestamp = new Date().toISOString();
  const signature = "sha256=" + (await hmacSha256Hex(secret, id + timestamp + body));
  return new Request("https://keysbot.example/twitch", {
    method: "POST",
    headers: {
      "Twitch-Eventsub-Message-Id": id,
      "Twitch-Eventsub-Message-Timestamp": timestamp,
      "Twitch-Eventsub-Message-Signature": signature,
      "Twitch-Eventsub-Message-Type": type,
    },
    body,
  });
}

const online = (broadcaster = "1234") => ({
  subscription: { type: "stream.online" },
  event: {
    type: "live",
    broadcaster_user_id: broadcaster,
    broadcaster_user_login: "keystrokeg",
    broadcaster_user_name: "KeystrokeG",
  },
});

test("twitch: answers the verification challenge", async () => {
  const res = await worker.fetch(await twitchRequest("webhook_callback_verification", { challenge: "abc123" }), env, ctx());
  assert.equal(res.status, 200);
  assert.equal(await res.text(), "abc123");
});

test("twitch: going live posts the announcement with title and game", async () => {
  const c = ctx();
  const res = await worker.fetch(await twitchRequest("notification", online()), env, c);
  assert.equal(res.status, 204);
  await c.settle();

  const [msg] = posted;
  assert.equal(msg.channelId, "900");
  assert.deepEqual(msg.allowed_mentions, { roles: ["111"] });
  assert.equal(
    msg.content,
    "<:twitch:1> <@&111> **¡KeystrokeG está en directo!**\n**Probando AION 2**\n🎮 AION 2\nhttps://twitch.tv/keystrokeg",
  );
});

test("twitch: a reconnect inside the cooldown stays quiet", async () => {
  channelHistory["900"] = [{ id: "m", timestamp: new Date(Date.now() - 20 * 60 * 1000).toISOString() }];
  const c = ctx();
  await worker.fetch(await twitchRequest("notification", online()), env, c);
  await c.settle();
  assert.equal(posted.length, 0);
});

test("twitch: announces again once the cooldown has passed", async () => {
  channelHistory["900"] = [{ id: "m", timestamp: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString() }];
  const c = ctx();
  await worker.fetch(await twitchRequest("notification", online()), env, c);
  await c.settle();
  assert.equal(posted.length, 1);
});

test("twitch: someone else's stream or a bad signature posts nothing", async () => {
  const c = ctx();
  let res = await worker.fetch(await twitchRequest("notification", online("999")), env, c);
  assert.equal(res.status, 204);
  res = await worker.fetch(await twitchRequest("notification", online(), { secret: "x".repeat(20) }), env, c);
  assert.equal(res.status, 401);
  await c.settle();
  assert.equal(posted.length, 0);
});

// ── Discord interactions are untouched ───────────────────────────────────────

test("root: an unsigned interaction is still a 401", async () => {
  const res = await worker.fetch(new Request("https://keysbot.example/", { method: "POST", body: "{}" }), env, ctx());
  assert.equal(res.status, 401);
});
