"""Regression: booking completes via salon-search and service-search paths."""
from __future__ import annotations
import sys, uuid, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

B = "http://127.0.0.1:8000"

def chat(s: str, m: str) -> dict:
    r = httpx.post(B + "/chat", json={"session_id": s, "message": m}, timeout=120)
    return r.json() if r.status_code == 200 else {"reply": "<503>", "recommendations": []}

def flow(label: str, msgs: list[str]) -> None:
    s = "t-" + uuid.uuid4().hex[:6]
    print(f"\n=== {label} ===")
    for m in msgs:
        d = chat(s, m)
        recs = d.get("recommendations") or []
        bp = (d.get("structured") or {}).get("booking_payload") or {}
        tag = f" [{len(recs)} cards]" if recs else ""
        first_line = d.get("reply", "").splitlines()[0] if d.get("reply") else ""
        print(f"  U: {m}")
        print(f"  B: {first_line}{tag}")
        if bp.get("time"):
            print(f"     PAYLOAD: salon_id={bp.get('salon_id')} service={bp.get('service')} "
                  f"category={bp.get('category')} date={bp.get('date')} time={bp.get('time')}")

flow("Salon-search -> select salon -> book", ["Show vendors in Noida", "proceed with prem", "26 July 2026", "3 PM"])
flow("Service-search + location -> book", ["Hair Smoothing in Noida", "25 July 2026", "4 PM"])
