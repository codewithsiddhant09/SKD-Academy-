from __future__ import annotations

import json
from collections import defaultdict

import app.services.category_service as category_module
import app.services.salon_service as salon_module

api_hit_counter = defaultdict(int)


MOCK_CATEGORIES = [
    {"id": "1", "name": "Hair"},
    {"id": "2", "name": "Body"},
    {"id": "3", "name": "Nails"},
    {"id": "4", "name": "Face"},
    {"id": "5", "name": "Makeup"},
    {"id": "6", "name": "Henna"},
    {"id": "7", "name": "Hair Removal"},
    {"id": "8", "name": "Bath Treatment"},
]


def fake_get_json(url: str):
    if "allCategories" in url:
        api_hit_counter["GET /user/allCategories"] += 1
        return MOCK_CATEGORIES
    if "viewVendor" in url:
        api_hit_counter["GET /user/viewVendor/{vendorId}"] += 1
        return {"id": "101", "name": "Mock Vendor"}
    api_hit_counter[f"GET unknown {url}"] += 1
    return {}


category_module.get_json = fake_get_json
salon_module.get_json = fake_get_json

from fastapi.testclient import TestClient
from app.main import app
from app.api import deps


def run() -> None:
    deps.initialize_dependencies()
    results = []

    with TestClient(app) as client:
        r = client.get("/health")
        results.append(("health", r.status_code, r.json()))

        r = client.get("/categories")
        results.append(("categories", r.status_code, r.json()))

        r = client.post("/chat", json={"session_id": "s1", "message": "I want hair smoothing"})
        results.append(("chat_service_no_location", r.status_code, r.json()))

        r = client.post("/chat", json={"session_id": "s1", "message": "Dubai Marina"})
        results.append(("chat_followup_location_only", r.status_code, r.json()))

        r = client.post("/chat", json={"session_id": "s2", "message": "I want hair smoothing in Dubai Marina"})
        results.append(("chat_service_with_location", r.status_code, r.json()))

        r = client.post("/chat", json={"session_id": "s3", "message": "Can I cancel my appointment?"})
        results.append(("chat_faq_cancel", r.status_code, r.json()))

        r = client.post("/chat", json={"session_id": "s4", "message": "Book appointment"})
        results.append(("chat_booking_start", r.status_code, r.json()))

        booking_details = (
            "name: Sara Khan, +971501234567, salon Marina Luxe Salon, "
            "service Hair Smoothing, 2026-06-15 18:30"
        )
        r = client.post("/chat", json={"session_id": "s4", "message": booking_details})
        results.append(("chat_booking_complete", r.status_code, r.json()))

        r = client.post(
            "/book-appointment",
            json={"session_id": "s5", "customer_name": "Sara"},
        )
        results.append(("book_appointment_missing_fields", r.status_code, r.json()))

        r = client.post(
            "/book-appointment",
            json={
                "session_id": "s5",
                "customer_name": "Sara Khan",
                "phone": "+971501234567",
                "salon": "Marina Luxe Salon",
                "service": "Hair Smoothing",
                "date": "2026-06-15",
                "time": "18:30",
            },
        )
        results.append(("book_appointment_success", r.status_code, r.json()))

        r = client.post("/chat", json={"session_id": "s6", "message": ""})
        results.append(("chat_empty_message", r.status_code, r.json()))

    report = {
        "scenario_results": [
            {"scenario": name, "status_code": code, "response": payload}
            for name, code, payload in results
        ],
        "api_hits": dict(api_hit_counter),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
