"""HTTP-level verification of the userId 500 fix (backend on :8000)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402

s = get_settings()
client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60.0)
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def wait_ready() -> None:
    for _ in range(20):
        try:
            if client.get("/health").json().get("status") == "ok":
                # also wait for orchestrator init
                r = client.post("/chat", json={"session_id": "warm", "message": "hi"})
                if r.status_code == 200:
                    return
        except Exception:
            pass
        time.sleep(1)


def main() -> int:
    from bson import ObjectId
    from pymongo import MongoClient

    db = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=8000)[s.mongodb_db_name]
    real_uid = str(db[s.mongodb_users_collection].find_one({"userType": "Vendor"})["_id"])
    missing_uid = str(ObjectId())

    wait_ready()

    # /chat with a real userId -> 200 (was 500)
    r = client.post("/chat", json={"session_id": "u1", "message": "hello", "user_id": real_uid})
    record("/chat real userId -> 200", r.status_code == 200, f"status={r.status_code}")

    # /chat with invalid userId -> 200 (graceful)
    r = client.post("/chat", json={"session_id": "u2", "message": "hello", "user_id": "bad-oid"})
    record("/chat invalid userId -> 200 (graceful)", r.status_code == 200, f"status={r.status_code}")

    # /session/start with a real userId -> 200
    r = client.post("/session/start", json={"session_id": "u3", "user_id": real_uid})
    record("/session/start real userId -> 200", r.status_code == 200, f"status={r.status_code}")

    # /session/start with non-existent valid ObjectId -> 404 (not 500)
    r = client.post("/session/start", json={"session_id": "u4", "user_id": missing_uid})
    record("/session/start missing user -> 404", r.status_code == 404, f"status={r.status_code}")

    # /session/start without userId -> 200 generic
    r = client.post("/session/start", json={"session_id": "u5"})
    record("/session/start no userId -> 200", r.status_code == 200, f"status={r.status_code}")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n======== RESULT: {passed}/{len(results)} PASSED ========")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
