from __future__ import annotations

import re

from app.models.schemas import BookingPayload


class BookingAgent:
    REQUIRED_FIELDS = ["salon", "service", "date", "time"]

    def extract_date_and_time(self, text: str, current: BookingPayload) -> BookingPayload:
        """Extract ONLY date and time from user message. Skip name, phone, email."""
        payload = current.model_copy(deep=True)

        # Extract date: support formats like "15 July 2026", "15/07/2026", "2026-07-15"
        date_patterns = [
            r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b",
            r"\b(\d{4}-\d{2}-\d{2})\b",
            r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                payload.date = match.group(1).strip()
                break

        # Extract time: support formats like "4 PM", "16:00", "4:00 PM", "3:30 PM".
        # The HH:MM pattern must be tried first; otherwise "3:30 PM" would be
        # mis-parsed as "30 PM" by the bare hour pattern.
        time_patterns = [
            r"\b(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)\b",
            r"\b(\d{1,2}\s*(?:AM|PM|am|pm))\b",
        ]
        for pattern in time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                payload.time = match.group(1).strip()
                break

        return payload

    def extract_fields(self, text: str, current: BookingPayload) -> BookingPayload:
        """Legacy method - now delegates to extract_date_and_time for simplified booking."""
        return self.extract_date_and_time(text, current)

    def missing_fields(self, payload: BookingPayload) -> list[str]:
        return [field for field in self.REQUIRED_FIELDS if not getattr(payload, field)]
