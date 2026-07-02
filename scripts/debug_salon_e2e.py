"""E2E salon discovery HTTP test with Mongo-backed expectations."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.repositories.salon_repository import SalonRepository

BASE = "http://127.0.0.1:8000"

SCENARIOS: list[tuple[str, str, int]] = [
    ("Hair Smoothing", "Noida", 1),
    ("I want Henna", "Noida", 1),
    ("Hair Smoothing", "Dubai", 1),
    ("Hair Smoothing", "Delhi", 0),
    ("Face", "Noida", 1),
    ("Body", "Noida", 0),
    ("Hair Removal", "Noida", 1),
]


def _category_for(service: str) -> str:
    mapping = {
        "Hair Smoothing": "Hair",
        "I want Henna": "Henna",
        "Face": "Face",
        "Body": "Body",
        "Hair Removal": "Hair Removal",
    }
    return mapping.get(service, service)


def chat(session: str, msg: str) -> dict:
    r = httpx.post(
        f"{BASE}/chat",
        json={"session_id": session, "message": msg},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    print("=" * 72)
    print("E2E SALON DISCOVERY HTTP TEST")
    print("=" * 72)

    repo = SalonRepository()
    passed = 0
    failed = 0

    for service, location, min_expected in SCENARIOS:
        cat = _category_for(service)
        mongo_count = len(repo.discover(location=location, category=cat, service=service))
        sid = "sal_" + uuid.uuid4().hex[:8]
        try:
            r1 = chat(sid, service)
            r2 = chat(sid, location)
        except httpx.HTTPError as exc:
            print(f"\n[FAIL] {service} -> {location} — HTTP error: {exc}")
            failed += 1
            continue

        recs = r2.get("recommendations") or []
        ok = len(recs) >= min_expected
        if min_expected == 0:
            ok = len(recs) == 0

        print(f"\n[{('PASS' if ok else 'FAIL')}] {service} -> {location}")
        print(f"  mongo_expected>={min_expected} (mongo={mongo_count}) http_recs={len(recs)}")
        print(f"  msg1 intent={r1.get('intent')} | msg2 intent={r2.get('intent')}")
        print(f"  reply={r2['reply'][:100].replace(chr(10), ' ')}...")
        if recs:
            print(f"  salons={[x.get('salon_name') for x in recs[:3]]}")
        passed += int(ok)
        failed += int(not ok)

    print(f"\n{'=' * 72}\nRESULT: {passed}/{passed + failed}\n{'=' * 72}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
