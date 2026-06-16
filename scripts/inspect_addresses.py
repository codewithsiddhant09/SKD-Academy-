"""Phase 1 schema inspection for the MongoDB `addresses` collection.

Connects using MONGODB_URI from the environment / .env, samples documents,
and prints a schema report. It makes no assumptions about field names —
it reports the actual keys/types found in real documents.

Usage:
    python scripts/inspect_addresses.py
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("MONGODB_DB_NAME", "bookly")
COLLECTION = os.getenv("MONGODB_ADDRESSES_COLLECTION", "addresses")
URI = os.getenv("MONGODB_URI", "")

SAMPLE_SIZE = 50


def _type_name(value: Any) -> str:
    return type(value).__name__


def main() -> None:
    if not URI:
        raise SystemExit("MONGODB_URI is not set. Add it to .env and re-run.")

    from pymongo import MongoClient

    client = MongoClient(URI, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    print("Mongo Connected")

    db = client[DB_NAME]
    collection = db[COLLECTION]

    total = collection.estimated_document_count()
    print(f"Database: {DB_NAME} | Collection: {COLLECTION} | est. documents: {total}")

    docs = list(collection.find({}).limit(SAMPLE_SIZE))
    print(f"Sampled documents: {len(docs)}")
    if not docs:
        print("No documents found in collection.")
        return

    field_presence: Counter[str] = Counter()
    field_types: dict[str, Counter[str]] = defaultdict(Counter)
    field_examples: dict[str, Any] = {}

    def walk(prefix: str, obj: Any) -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                path = f"{prefix}.{key}" if prefix else key
                field_presence[path] += 1
                field_types[path][_type_name(val)] += 1
                if path not in field_examples and not isinstance(val, (dict, list)):
                    field_examples[path] = val
                if isinstance(val, dict):
                    walk(path, val)
                elif isinstance(val, list) and val:
                    field_types[path]["list"] += 0
                    if path not in field_examples:
                        field_examples[path] = val[:3]
                    if isinstance(val[0], dict):
                        walk(f"{path}[]", val[0])

    for doc in docs:
        walk("", doc)

    print("\n================ SCHEMA REPORT ================")
    print(f"{'field':45} {'present':>8} {'types'}")
    print("-" * 90)
    for field in sorted(field_presence):
        types = ", ".join(f"{t}:{c}" for t, c in field_types[field].items() if c)
        print(f"{field:45} {field_presence[field]:>8} {types}")

    print("\n================ FIELD EXAMPLES ================")
    for field in sorted(field_examples):
        example = field_examples[field]
        text = str(example)
        if len(text) > 80:
            text = text[:77] + "..."
        print(f"{field:45} = {text}")

    print("\n================ ONE FULL SAMPLE DOC ================")
    import json

    def default(o: Any) -> str:
        return str(o)

    print(json.dumps(docs[0], indent=2, default=default)[:4000])

    print("\nSchema Loaded")


if __name__ == "__main__":
    main()
