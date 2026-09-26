/** Discord REST helpers shared by the button handler and the announcements. */

const API = "https://discord.com/api/v10";

export async function discord(env, method, path, body) {
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
export async function log(env, text) {
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

/** name → "<:name:id>" for the app's own emojis (uploaded by upload_emojis.py). */
export async function appEmojis(env) {
  try {
    const app = await (await discord(env, "GET", "/applications/@me")).json();
    const { items } = await (await discord(env, "GET", `/applications/${app.id}/emojis`)).json();
    return Object.fromEntries(items.map((e) => [e.name, `<:${e.name}:${e.id}>`]));
  } catch (err) {
    // An announcement without logos beats no announcement.
    console.error(`no se pudieron leer los emojis de la app: ${err.message}`);
    return {};
  }
}

/** The channel's latest messages, newest first. */
export async function recentMessages(env, channelId, limit) {
  const res = await discord(env, "GET", `/channels/${channelId}/messages?limit=${limit}`);
  return res.json();
}
