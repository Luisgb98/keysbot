/** HMAC-SHA256 signatures for the Twitch and hub webhooks. */

const encoder = new TextEncoder();

export async function hmacSha256Hex(secret, message) {
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time string comparison. */
export function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string") return false;
  const x = encoder.encode(a);
  const y = encoder.encode(b);
  if (x.length !== y.length) return false;
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return diff === 0;
}

/** Whether a unix-seconds or ISO timestamp is within `maxAgeSeconds` of now. */
export function isFresh(timestamp, maxAgeSeconds, now = Date.now()) {
  const ms = /^\d+$/.test(timestamp ?? "") ? Number(timestamp) * 1000 : Date.parse(timestamp);
  return Number.isFinite(ms) && Math.abs(now - ms) <= maxAgeSeconds * 1000;
}
