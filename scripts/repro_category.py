from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60.0)

PHRASES = [
    "give me category list",
    "list categories",
    "show categories",
    "what categories are available",
    "available services",
    "what services do you offer",
    "category",
    "categories",
    "category list",
    "available categories",
    "service categories",
    "services available",
    "give me all categories",
    "give me the list of categories",
    "list all services",
]

for p in PHRASES:
    r = client.post("/chat", json={"session_id": "c_" + uuid.uuid4().hex[:6], "message": p})
    j = r.json()
    intent = str(j.get("intent", "")).split(".")[-1].lower()
    reply = j["reply"].replace("\n", " ")
    ok = intent == "category_list"
    print(f"[{'OK ' if ok else 'BAD'}] {p!r:40s} intent={intent:18s} reply={reply[:55]!r}")
