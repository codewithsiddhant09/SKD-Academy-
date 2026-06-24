"""Inspect bookings collection schema."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import get_settings
from pymongo import MongoClient

s = get_settings()
db = MongoClient(s.mongodb_uri)[s.mongodb_db_name]
doc = db["bookings"].find_one()
print("Sample booking keys:", sorted(doc.keys()) if doc else "none")
if doc:
    for k in sorted(doc.keys()):
        print(f"  {k}: {type(doc[k]).__name__} = {str(doc[k])[:60]!r}")
