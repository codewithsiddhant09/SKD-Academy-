"""Verify the new intent classification + entity extraction for all 7 scenarios."""
from __future__ import annotations
import sys, uuid, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"

import time

def chat(session: str, msg: str) -> dict:
    for _ in range(8):
        r = httpx.post(f"{BASE}/chat", json={"session_id": session, "message": msg}, timeout=120)
        if r.status_code == 200:
            return r.json()
        time.sleep(3)  # server reloading; retry
    return {"reply": "<server unavailable>", "intent": "?", "recommendations": []}


def wait_ready() -> None:
    for _ in range(30):
        try:
            h = httpx.get(f"{BASE}/health", timeout=10).json()
            if h.get("categories_cached"):
                # one warmup chat to trigger lazy init
                httpx.post(f"{BASE}/chat", json={"session_id": "warmup", "message": "hi"}, timeout=120)
                return
        except Exception:
            pass
        time.sleep(3)

SCENARIOS = [
    ("1. Show salons in Noida",      "Show salons in Noida",                         "SALON_SEARCH -> cards, no category"),
    ("2. Show vendors in Noida",     "Show vendors in Noida",                        "SALON_SEARCH -> cards, no category"),
    ("3. Hair Smoothing",           "Hair Smoothing",                                "SERVICE_SEARCH -> ask location"),
    ("4. Hair Smoothing in Noida",  "Hair Smoothing in Noida",                       "SERVICE_SEARCH + location -> cards"),
    ("5. Bridal Makeup in Dubai",   "Bridal Makeup in Dubai",                        "SERVICE_SEARCH + location -> cards/mock"),
    ("6. What is Bookly?",          "What is Bookly?",                               "FAQ -> RAG"),
    ("7. Payment methods",          "What payment methods are supported?",           "FAQ -> RAG"),
    ("8. Vendor list edge",         "Give the list of vendor who can provide service in Noida", "SALON_SEARCH -> cards"),
]

wait_ready()
print("=" * 78)
for label, msg, expected in SCENARIOS:
    s = "t-" + uuid.uuid4().hex[:6]
    d = chat(s, msg)
    recs = d.get("recommendations") or []
    intent = d.get("intent")
    struct = d.get("structured") or {}
    reply = d.get("reply", "<no reply>").replace("\n", " ")
    print(f"\n{label}")
    print(f"  msg     : {msg}")
    print(f"  expect  : {expected}")
    print(f"  intent  : {intent}")
    print(f"  cards   : {len(recs)} {[r.get('salon_name') for r in recs]}")
    print(f"  reply   : {reply[:120]}")
print("\n" + "=" * 78)
