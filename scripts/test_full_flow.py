"""Comprehensive booking + edge-case + efficiency test against the live API."""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE = "http://127.0.0.1:8000"


def chat(session_id: str, message: str) -> dict:
    r = httpx.post(
        f"{BASE}/chat",
        json={"session_id": session_id, "message": message},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()


def sid() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


def line(reply: str, n: int = 95) -> str:
    return reply.replace("\n", " ")[:n]


def scenario(title: str, steps: list[tuple[str, str]]) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    s = sid()
    for who, msg in steps:
        d = chat(s, msg)
        recs = d.get("recommendations") or []
        tag = f" [{len(recs)} cards]" if recs else ""
        print(f"USER: {msg}")
        print(f"BOT : {line(d['reply'])}{tag}")
        if recs:
            for r in recs[:3]:
                print(f"      - {r.get('salon_name')} | {r.get('location')} | rating={r.get('rating')} | {r.get('redirect_url')}")
        bp = (d.get("structured") or {}).get("booking_payload")
        if bp and bp.get("date") and bp.get("time"):
            print(f"      PAYLOAD: salon_id={bp.get('salon_id')} service={bp.get('service')} category={bp.get('category')} date={bp.get('date')} time={bp.get('time')} user_id={bp.get('user_id')}")


def main() -> None:
    print("Health:", httpx.get(f"{BASE}/health", timeout=15).json())

    # 1) Happy path, real MongoDB salon (Noida)
    scenario("S1: Happy path - real MongoDB salon (Hair -> Noida -> date -> time)", [
        ("u", "I want Hair"),
        ("u", "Noida"),
        ("u", "20 July 2026"),
        ("u", "4 PM"),
    ])

    # 2) UAE input -> mock fallback
    scenario("S2: UAE input -> mock fallback (Hair Smoothing -> Dubai)", [
        ("u", "I want Hair Smoothing"),
        ("u", "Dubai Marina"),
        ("u", "15 July 2026"),
        ("u", "2 PM"),
    ])

    # 3) No match anywhere -> 'no salons' path
    scenario("S3: No match (Bridal Makeup -> Sharjah)", [
        ("u", "I need Bridal Makeup"),
        ("u", "Sharjah"),
    ])

    # 4) Service + location in one message
    scenario("S4: Service + location single message (Makeup in India)", [
        ("u", "I want Makeup in India"),
    ])

    # 5) FAQ interrupt mid-flow (should not break booking state)
    scenario("S5: FAQ in the middle of discovery", [
        ("u", "I want Hair"),
        ("u", "What is the cancellation policy?"),
        ("u", "Noida"),
        ("u", "22 August 2026"),
        ("u", "11 AM"),
    ])

    # 6) Time given before date (out-of-order)
    scenario("S6: Time before date (out-of-order entry)", [
        ("u", "I want Hair"),
        ("u", "Noida"),
        ("u", "5 PM"),
        ("u", "25 July 2026"),
    ])

    # 7) Pure greeting / general
    scenario("S7: Greeting only", [
        ("u", "Hello"),
    ])

    # 8) Unknown service
    scenario("S8: Unknown / nonsense service", [
        ("u", "I want xyz123 service"),
        ("u", "Noida"),
    ])

    # 9) Date in different format
    scenario("S9: Numeric date format (Hair -> Noida -> 2026-07-30)", [
        ("u", "I want Hair"),
        ("u", "Noida"),
        ("u", "2026-07-30"),
        ("u", "3:30 PM"),
    ])

    # 10) Empty-ish / vague
    scenario("S10: Vague booking request", [
        ("u", "I want to book an appointment"),
    ])


if __name__ == "__main__":
    t = time.time()
    main()
    print(f"\nAll scenarios completed in {time.time()-t:.1f}s")
