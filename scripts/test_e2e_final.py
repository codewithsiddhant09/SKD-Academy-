"""Final E2E validation after all fixes."""
from __future__ import annotations
import sys, uuid, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"

def chat(session: str, msg: str) -> dict:
    return httpx.post(f"{BASE}/chat", json={"session_id": session, "message": msg}, timeout=120).json()

def flow(label: str, msgs: list[str]) -> None:
    s = "t-" + uuid.uuid4().hex[:6]
    print(f"\n{'='*65}")
    print(f"FLOW: {label}")
    print("="*65)
    for m in msgs:
        d = chat(s, m)
        recs = d.get("recommendations") or []
        names = [r.get("salon_name") for r in recs]
        bp = (d.get("structured") or {}).get("booking_payload") or {}
        print(f"  USER: {m}")
        print(f"  BOT : {d['reply'][:110].replace(chr(10),' ')}")
        if recs:
            print(f"  CARDS [{len(recs)}]: {names}")
        if bp.get("time"):
            print(f"  PAYLOAD: salon_id={bp.get('salon_id')} service={bp.get('service')} date={bp.get('date')} time={bp.get('time')}")

flow("Test 1 — Hair Smoothing + Noida (MongoDB)", ["I want Hair Smoothing", "Noida"])
flow("Test 2 — Hair Coloring + Noida (MongoDB)", ["I want Hair Coloring", "Noida"])
flow("Test 3 — RAG: What is Bookly?", ["What is Bookly?"])
flow("Test 4 — Full booking flow Noida", ["I want Hair", "Noida", "25 July 2026", "4 PM"])
flow("Test 5 — UAE fallback (mock)", ["I want Hair Smoothing", "Dubai Marina"])
flow("Test 6 — No salons path (Gurgaon)", ["I want Bridal Makeup", "Gurgaon"])
