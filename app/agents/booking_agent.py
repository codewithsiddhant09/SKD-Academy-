from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.core.logging import get_logger
from app.models.schemas import BookingPayload
from app.utils.text import title_case_safe

logger = get_logger(__name__)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_SERVICE_KEYWORDS = (
    "hair",
    "makeup",
    "facial",
    "wax",
    "waxing",
    "pedicure",
    "manicure",
    "massage",
    "nails",
    "henna",
    "spa",
    "bridal",
    "body",
    "smoothing",
    "trim",
    "color",
    "colour",
    "threading",
)

_DATETIME_STRIP_PATTERNS = (
    r"\bon\s+\d{1,2}/\d{1,2}/\d{4}\b",
    r"\bon\s+\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4}\b",
    r"\b\d{1,2}/\d{1,2}/\d{4}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)\b",
    r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b",
    r"\b\d{1,2}\s*(?:AM|PM|am|pm)\b",
    r"\b(?:tomorrow|today)\b",
    r"\bon\s+(?:tomorrow|today)\b",
)


class BookingAgent:
    REQUIRED_FIELDS = ["salon", "service", "date", "time"]

    @staticmethod
    def format_display_date(value: date) -> str:
        return f"{value.day} {_MONTH_NAMES[value.month - 1]} {value.year}"

    @staticmethod
    def parse_date(value: str | None) -> date | None:
        """Parse a supported date string into a date object, or None."""
        if not value:
            return None
        text = value.strip()

        m = re.search(
            r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+(\d{4})\b",
            text,
            re.IGNORECASE,
        )
        if m:
            day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            try:
                return date(year, _MONTHS[month_name], day)
            except ValueError:
                return None

        m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None

        m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                return None

        return None

    def extract_relative_date(self, text: str, today: date | None = None) -> str | None:
        lower = text.lower()
        reference = today or datetime.now().date()
        if re.search(r"\btomorrow\b", lower):
            return self.format_display_date(reference + timedelta(days=1))
        if re.search(r"\btoday\b", lower):
            return self.format_display_date(reference)
        return None

    def is_past_date(self, value: str | None, today: date | None = None) -> bool:
        parsed = self.parse_date(value)
        if parsed is None:
            return False
        reference = today or datetime.now().date()
        return parsed < reference

    @staticmethod
    def _has_service_keyword(text: str) -> bool:
        lower = text.lower()
        return any(keyword in lower for keyword in _SERVICE_KEYWORDS)

    def _looks_like_time(self, value: str | None) -> bool:
        if not value:
            return False
        return bool(re.match(r"^\d{1,2}(:\d{2})?\s*(?:AM|PM|am|pm)$", value.strip()))

    def _is_valid_time(self, value: str | None) -> bool:
        if not value or not value.strip():
            return False
        return bool(
            re.match(r"^\d{1,2}(:\d{2})?\s*(?:AM|PM|am|pm)$", value.strip())
        )

    def _is_valid_date(self, value: str | None) -> bool:
        if not value or not value.strip():
            return False
        return self.parse_date(value) is not None or value.lower() in {"tomorrow", "today"}

    def _is_valid_salon_name(self, value: str | None) -> bool:
        if not value or len(value.strip()) < 2:
            return False
        text = value.strip()
        if self._looks_like_time(text):
            return False
        if self._is_valid_date(text):
            return False
        if re.match(r"^\d+(?::\d{2})?\s*(?:am|pm)?$", text, re.IGNORECASE):
            return False
        if re.search(r"\b(?:appointment|book(?:ing)?)\b", text, re.IGNORECASE):
            return False
        return True

    def _strip_datetime_tokens(self, text: str) -> str:
        cleaned = text
        for pattern in _DATETIME_STRIP_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", cleaned).strip(" .,-")

    def _salon_extraction_text(self, text: str) -> str:
        cleaned = self._strip_datetime_tokens(text)
        parts = re.split(
            r"\.\s+(?=(?:i want|i need|i would like|book|please)\b)",
            cleaned,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        return parts[0].strip(" .,-")

    def extract_salon_from_message(
        self,
        text: str,
        salon_lookup: dict[str, str] | None = None,
    ) -> tuple[str | None, str | None]:
        salon_lookup = salon_lookup or {}
        source = self._salon_extraction_text(text)
        text_lower = source.lower()

        for name, sid in salon_lookup.items():
            if name in text_lower:
                return title_case_safe(name), sid or None

        patterns = [
            r"\b(?:book(?:\s+it)?|appointment(?:\s+request)?)\s+(?:at|with)\s+(?P<salon>[A-Za-z0-9][A-Za-z0-9\s&'.-]{1,80}?)\s*$",
            r"\bat\s+(?P<salon>[A-Za-z0-9][A-Za-z0-9\s&'.-]{1,80}?)\s*$",
            r"\bat\s+(?P<salon>[A-Za-z0-9][A-Za-z0-9\s&'.-]{1,80}?)(?:\s+(?:in|near)\s+[A-Za-z0-9\s&'.-]{1,40})?\s*$",
        ]
        for pattern in patterns:
            match = re.search(pattern, source, re.IGNORECASE)
            if not match:
                continue
            salon = match.group("salon").strip(" .,-")
            if not self._is_valid_salon_name(salon):
                continue
            key = salon.lower()
            sid = salon_lookup.get(key)
            return title_case_safe(salon), sid or None

        if "salon" in text_lower or "prem" in text_lower:
            match = re.search(
                r"\b((?:[A-Za-z0-9][A-Za-z0-9\s&'.-]*\s)?[A-Za-z0-9][A-Za-z0-9\s&'.-]*Salon(?:\s+[A-Za-z0-9\s&'.-]{1,40})?)\b",
                source,
                re.IGNORECASE,
            )
            if match:
                salon = match.group(1).strip(" .,-")
                if self._is_valid_salon_name(salon):
                    key = salon.lower()
                    sid = salon_lookup.get(key)
                    return title_case_safe(salon), sid or None

        return None, None

    def extract_service_from_message(self, text: str) -> str | None:
        source = self._salon_extraction_text(text)
        patterns = [
            r"(?:i want|i need|i would like|book|get|looking for)\s+(?P<service>.+?)(?:\s+at\s+|\s+on\s+|\s+tomorrow|\s+today|\s+\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"(?:book|schedule)\s+(?P<service>.+?)\s+at\s+",
            r"^(?P<service>(?:[A-Za-z]+\s+)*[A-Za-z]+)\s+(?:on|at)\s+",
        ]
        for pattern in patterns:
            match = re.search(pattern, source, re.IGNORECASE)
            if not match:
                continue
            service = match.group("service").strip(" .,-")
            service = re.sub(r"\s+appointment.*$", "", service, flags=re.IGNORECASE).strip()
            if service and self._has_service_keyword(service):
                return service

        if self._has_service_keyword(source):
            cleaned = re.sub(
                r"\b(i want|i need|i would like|i'd like|looking for|book|reserve|please|"
                r"give me|can i get|get me|i am looking for|show me)\b",
                "",
                source,
                flags=re.IGNORECASE,
            ).strip(" .,-")
            cleaned = re.sub(r"\s+at\s+.+$", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"\s+on\s+.+$", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"\s+tomorrow.*$", "", cleaned, flags=re.IGNORECASE).strip()
            if cleaned and self._has_service_keyword(cleaned):
                return cleaned
        return None

    def extract_date_and_time(self, text: str, current: BookingPayload) -> BookingPayload:
        payload = current.model_copy(deep=True)

        relative = self.extract_relative_date(text)
        if relative:
            payload.date = relative

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

    def extract_booking_fields(
        self,
        text: str,
        current: BookingPayload,
        salon_lookup: dict[str, str] | None = None,
    ) -> BookingPayload:
        payload = self.extract_date_and_time(text, current)

        service = self.extract_service_from_message(text)
        if service:
            payload.service = service

        salon, salon_id = self.extract_salon_from_message(text, salon_lookup)
        if salon and self._is_valid_salon_name(salon):
            payload.salon = salon
            if salon_id:
                payload.salon_id = salon_id
        elif payload.salon and not self._is_valid_salon_name(payload.salon):
            payload.salon = None
            payload.salon_id = None

        return payload

    def extract_fields(self, text: str, current: BookingPayload) -> BookingPayload:
        return self.extract_booking_fields(text, current)

    def booking_data_completeness_check(
        self,
        payload: BookingPayload,
    ) -> tuple[bool, list[str]]:
        """Return (is_complete, missing_fields) after validating extracted values."""
        missing: list[str] = []

        if not payload.service or not str(payload.service).strip():
            missing.append("service")
        if not self._is_valid_salon_name(payload.salon):
            missing.append("salon")
        if not self._is_valid_date(payload.date):
            missing.append("date")
        if not self._is_valid_time(payload.time):
            missing.append("time")

        is_complete = len(missing) == 0
        logger.info(
            "BOOKING_COMPLETENESS: complete=%s missing=%s service=%s salon=%s date=%s time=%s",
            is_complete,
            missing,
            payload.service,
            payload.salon,
            payload.date,
            payload.time,
        )
        return is_complete, missing

    def log_detected_entities(self, payload: BookingPayload) -> None:
        logger.info(
            "BOOKING_EXTRACT: Detected Service=%s Salon=%s Date=%s Time=%s",
            payload.service,
            payload.salon,
            payload.date,
            payload.time,
        )

    def missing_fields(self, payload: BookingPayload) -> list[str]:
        _, missing = self.booking_data_completeness_check(payload)
        return missing

    def first_missing_field(self, payload: BookingPayload) -> str | None:
        _, missing = self.booking_data_completeness_check(payload)
        return missing[0] if missing else None
