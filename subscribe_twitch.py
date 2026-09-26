"""One-shot script: subscribe the Worker to Twitch's stream.online webhook.

    python subscribe_twitch.py

Run it after deploying the Worker with the TWITCH_* secrets set: Twitch sends
the Worker a verification challenge straight away, and only enables the
subscription if the Worker answers it. Safe to re-run — an enabled
subscription pointing at the same URL is left alone; a failed one is replaced.

Prints the channel's Twitch user ID for TWITCH_BROADCASTER_ID in
worker/wrangler.toml.
"""

import os
import sys
import time

import requests

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
EVENTSUB_SECRET = os.environ["TWITCH_EVENTSUB_SECRET"]
CHANNEL = os.environ["TWITCH_CHANNEL"]                 # login, e.g. keystrokeg
CALLBACK = os.environ["WORKER_URL"].rstrip("/") + "/twitch"

HELIX = "https://api.twitch.tv/helix"


def app_token():
    res = requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    }, timeout=30)
    if not res.ok:
        sys.exit(f"✗ No se pudo obtener el token de Twitch: HTTP {res.status_code}")
    return res.json()["access_token"]


def main():
    if len(EVENTSUB_SECRET) < 10:
        sys.exit("✗ TWITCH_EVENTSUB_SECRET debe tener entre 10 y 100 caracteres")

    headers = {"Client-Id": CLIENT_ID, "Authorization": f"Bearer {app_token()}"}

    res = requests.get(f"{HELIX}/users", params={"login": CHANNEL}, headers=headers, timeout=30)
    users = res.json().get("data") if res.ok else None
    if not users:
        sys.exit(f"✗ Canal de Twitch '{CHANNEL}' no encontrado")
    broadcaster_id = users[0]["id"]
    print(f"  → {users[0]['display_name']} (ID: {broadcaster_id})")

    res = requests.get(f"{HELIX}/eventsub/subscriptions", params={"type": "stream.online"},
                       headers=headers, timeout=30)
    if not res.ok:
        sys.exit(f"✗ No se pudieron listar las suscripciones: HTTP {res.status_code}: {res.text}")
    for sub in res.json()["data"]:
        if sub["condition"].get("broadcaster_user_id") != broadcaster_id:
            continue
        if sub["transport"].get("callback") == CALLBACK and sub["status"] == "enabled":
            print(f"  ↩ Suscripción ya activa (ID: {sub['id']})")
            return report(broadcaster_id)
        requests.delete(f"{HELIX}/eventsub/subscriptions", params={"id": sub["id"]},
                        headers=headers, timeout=30)
        print(f"  ! Suscripción anterior eliminada ({sub['status']}, {sub['transport'].get('callback')})")

    res = requests.post(f"{HELIX}/eventsub/subscriptions", headers=headers, timeout=30, json={
        "type": "stream.online",
        "version": "1",
        "condition": {"broadcaster_user_id": broadcaster_id},
        "transport": {"method": "webhook", "callback": CALLBACK, "secret": EVENTSUB_SECRET},
    })
    if not res.ok:
        sys.exit(f"✗ No se pudo crear la suscripción: HTTP {res.status_code}: {res.text}")
    sub = res.json()["data"][0]
    print(f"  ✓ Suscripción creada (ID: {sub['id']}) → {CALLBACK}")

    # Twitch verifies the callback within seconds; confirm the Worker passed.
    for _ in range(10):
        time.sleep(2)
        res = requests.get(f"{HELIX}/eventsub/subscriptions", params={"type": "stream.online"},
                           headers=headers, timeout=30)
        status = next((s["status"] for s in res.json()["data"] if s["id"] == sub["id"]), "missing")
        if status != "webhook_callback_verification_pending":
            break
    if status == "enabled":
        print("  ✓ Twitch ha verificado el Worker")
    else:
        print(f"  ✗ Estado de la suscripción: {status} — revisa `npx wrangler tail` y TWITCH_EVENTSUB_SECRET")
    report(broadcaster_id)


def report(broadcaster_id):
    print(f"\nEn worker/wrangler.toml: TWITCH_BROADCASTER_ID = \"{broadcaster_id}\"")


if __name__ == "__main__":
    main()
