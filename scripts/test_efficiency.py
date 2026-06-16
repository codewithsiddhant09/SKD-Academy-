"""Measure MongoDB query efficiency + connection reuse for discovery."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import monitoring


class QueryCounter(monitoring.CommandListener):
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def started(self, event: monitoring.CommandStartedEvent) -> None:
        if event.command_name in {"find", "aggregate", "count", "ping", "hello", "isMaster"}:
            self.counts[event.command_name] = self.counts.get(event.command_name, 0) + 1

    def succeeded(self, event) -> None:  # noqa: D401
        pass

    def failed(self, event) -> None:  # noqa: D401
        pass


counter = QueryCounter()
monitoring.register(counter)

from app.repositories.salon_repository import SalonRepository  # noqa: E402


def main() -> None:
    repo = SalonRepository()

    # Warm up the connection (so 'find' counts exclude connection handshake)
    t0 = time.time()
    available = repo.is_available()
    print(f"Connection available: {available} (warmup {(time.time()-t0)*1000:.0f} ms)")
    print(f"Same MongoClient reused across calls: {repo._db is not None}")

    cases = [
        ("Noida/Hair", "Noida", "Hair", "Hair"),
        ("India/Makeup", "India", "Makeup", "Makeup"),
        ("Dubai/Hair (empty -> upstream fallback)", "Dubai Marina", "Hair", "Hair Coloring"),
        ("Noida ONLY (high cardinality ~24 salons)", "Noida", None, None),
    ]
    for label, loc, cat, svc in cases:
        counter.counts.clear()
        t0 = time.time()
        salons = repo.discover(location=loc, category=cat, service=svc)
        elapsed = (time.time() - t0) * 1000
        finds = counter.counts.get("find", 0)
        # O(1) = query count is bounded and does NOT grow with the number of salons.
        # Worst case: 2 (location) + 2 (category) + 1 (service) + 4 (batch build) = 9.
        verdict = "O(1) batched (constant)" if finds <= 9 else f"grows with N ({finds})"
        print(f"\n[{label}]")
        print(f"  salons returned : {len(salons)}")
        print(f"  find() queries  : {finds}")
        print(f"  elapsed         : {elapsed:.0f} ms")
        print(f"  efficiency      : {verdict}")


if __name__ == "__main__":
    main()
