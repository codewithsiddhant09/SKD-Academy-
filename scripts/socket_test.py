"""Socket.IO live test against the running backend (port 8000).

Verifies: connection, bot_response (welcome), typing_start, typing_end,
bot_response (reply), salon_cards, and the booking confirmation message.

Run (backend must be running on :8000):
    python scripts/socket_test.py
"""
from __future__ import annotations

import time

import socketio

URL = "http://127.0.0.1:8000"
received: dict[str, list] = {
    "bot_response": [],
    "typing_start": [],
    "typing_end": [],
    "salon_cards": [],
}

sio = socketio.Client(logger=False, engineio_logger=False)


@sio.event
def connect() -> None:
    print("[event] connect -> OK")


@sio.event
def disconnect() -> None:
    print("[event] disconnect -> OK")


@sio.on("bot_response")
def on_bot_response(data) -> None:
    received["bot_response"].append(data)
    print(f"[event] bot_response: {str(data.get('reply'))[:70]!r}")


@sio.on("typing_start")
def on_typing_start(data) -> None:
    received["typing_start"].append(data)
    print("[event] typing_start")


@sio.on("typing_end")
def on_typing_end(data) -> None:
    received["typing_end"].append(data)
    print("[event] typing_end")


@sio.on("salon_cards")
def on_salon_cards(data) -> None:
    received["salon_cards"].append(data)
    salons = data.get("salons", [])
    print(f"[event] salon_cards: {len(salons)} cards; first image="
          f"{(salons[0].get('image') if salons else None)}")


def main() -> int:
    results: list[tuple[str, bool]] = []

    sio.connect(URL, transports=["websocket", "polling"], wait_timeout=15)
    time.sleep(1.5)
    results.append(("connection", sio.connected))
    results.append(("welcome bot_response", len(received["bot_response"]) >= 1))

    # Salon search -> expect typing_start, bot_response, salon_cards, typing_end
    sio.emit("user_message", {"session_id": "socktest", "message": "Show me salons in Noida"})
    time.sleep(6)
    results.append(("typing_start", len(received["typing_start"]) >= 1))
    results.append(("salon_cards", len(received["salon_cards"]) >= 1))
    results.append(("typing_end", len(received["typing_end"]) >= 1))

    # Booking flow -> confirmation arrives via bot_response
    for msg in ["I want Hair Smoothing", "Noida", "proceed", "15 December 2026", "4 PM"]:
        sio.emit("user_message", {"session_id": "sockbook", "message": msg})
        time.sleep(4)
    confirmed = any("booked" in str(d.get("reply", "")).lower() for d in received["bot_response"])
    results.append(("booking confirmation via bot_response", confirmed))

    sio.disconnect()
    time.sleep(0.5)

    print("\n==== SOCKET TEST REPORT ====")
    passed = 0
    for name, ok in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        passed += int(ok)
    print(f"RESULT: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
