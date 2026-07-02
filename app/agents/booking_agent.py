from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.core.logging import get_logger
from app.agents.category_agent import CategoryAgent
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
    "face",
    "wax",
    "waxing",
    "pedicure",
    "manicure",
    "nail",
    "nails",
    "massage",
    "henna",
    "spa",
    "bridal",
    "body",
    "smoothing",
    "trim",
    "color",
    "colour",
    "threading",
    "treatment",
    "keratin",
)

_GLUED_ON_DATE = re.compile(r"\bon(\d{1,2}/\d{1,2}/\d{4})\b", re.IGNORECASE)

_DATETIME_STRIP_PATTERNS = (
    r"\bon\d{1,2}/\d{1,2}/\d{4}\b",
    r"\bon\s+\d{1,2}/\d{1,2}/\d{4}\b",
    r"\bon\s+\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)(?:\s+\d{4})?\b",
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)(?:\s+\d{4})?\b",
    r"\b\d{1,2}/\d{1,2}/\d{4}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)\b",
    r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b",
    r"\b\d{1,2}\s*(?:AM|PM|am|pm)\b",
    r"\b(?:tomorrow|today)\b",
    r"\bon\s+(?:tomorrow|today)\b",
)


_BOOKING_FILLER_PATTERN = re.compile(
    r"\b(?:"
    r"i|want|need|please|book|booking|schedule|reserve|get|a|an|the|my|me|for|"
    r"session|appointment|services?|would|like|to|can|you|help|with|"
    r"looking|some|any"
    r")\b",
    re.IGNORECASE,
)


class BookingAgent:
    REQUIRED_FIELDS = ["salon", "service", "date", "time"]

    def __init__(
        self,
        categories: list[str] | None = None,
        category_agent: CategoryAgent | None = None,
    ) -> None:
        self.categories = categories or []
        self.category_agent = category_agent or CategoryAgent()

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

        m = _GLUED_ON_DATE.search(text)
        if m:
            text = m.group(1)

        m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                return None

        # "25 July" or "25 July 2026" — year optional
        m = re.search(
            r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)(?:\s+(\d{4}))?\b",
            text,
            re.IGNORECASE,
        )
        if m:
            day, month_name = int(m.group(1)), m.group(2).lower()
            year = int(m.group(3)) if m.group(3) else datetime.now().year
            try:
                parsed = date(year, _MONTHS[month_name], day)
                if not m.group(3) and parsed < datetime.now().date():
                    parsed = date(year + 1, _MONTHS[month_name], day)
                return parsed
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

    @staticmethod
    def _at_token_is_location(text: str, token: str) -> bool:
        """True when 'at <token>' is a city/area before date/time, not a salon name."""
        if not token or re.search(r"\bsalon\b", token, re.IGNORECASE):
            return False
        return bool(
            re.search(
                rf"\bat\s+{re.escape(token)}\s*(?:,|\s+on\d{{1,2}}/|\s+on\s+\d{{1,2}}/)",
                text,
                re.IGNORECASE,
            )
        )

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
            r"\bat\s+(?P<salon>(?:The\s+)?[A-Za-z0-9][A-Za-z0-9\s&'.-]{1,80}?)\s*$",
            r"\bat\s+(?P<salon>(?:The\s+)?[A-Za-z0-9][A-Za-z0-9\s&'.-]{1,80}?)(?:\s+(?:in|near)\s+[A-Za-z0-9\s&'.-]{1,40})?\s*$",
        ]
        for pattern in patterns:
            match = re.search(pattern, source, re.IGNORECASE)
            if not match:
                continue
            salon = match.group("salon").strip(" .,-")
            if self._at_token_is_location(text, salon):
                continue
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

    def _strip_booking_fillers(self, text: str) -> str:
        """Remove helper/filler words from a service phrase."""
        cleaned = text.strip(" .,-")
        cleaned = re.sub(
            r"^(?:please\s+)?(?:book|schedule|reserve)\s+(?:(?:a|an|the|my)\s+)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(_BOOKING_FILLER_PATTERN, " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip(" .,-")

    def _is_plausible_service(self, value: str | None) -> bool:
        if not value or len(value.strip()) < 2:
            return False
        text = value.strip().lower()
        if self._looks_like_time(value) or self._is_valid_date(value):
            return False
        filler_hits = sum(1 for w in text.split() if w in {
            "for", "me", "please", "book", "want", "need", "session", "appointment", "the", "my", "a", "an", "at",
        })
        if filler_hits >= 2:
            return False
        if len(text.split()) > 6:
            return False
        return self._has_service_keyword(value)

    def normalize_service_and_category(
        self, phrase: str
    ) -> tuple[str | None, str | None, bool]:
        """Return canonical (service, category, confident)."""
        cleaned = self._strip_booking_fillers(phrase)
        if not cleaned:
            return None, None, False

        canonical, category = self.category_agent.canonical_service_label(
            cleaned, self.categories
        )
        if canonical and self._is_plausible_service(canonical):
            return canonical, category, True

        if self._has_service_keyword(cleaned):
            mapped = self.category_agent.map_category(cleaned, self.categories)
            if mapped and len(cleaned.split()) <= 4:
                label = canonical or title_case_safe(cleaned)
                if self._is_plausible_service(label):
                    return label, mapped, True

        return None, None, False

    def extract_service_from_message(self, text: str) -> str | None:
        source = self._salon_extraction_text(text)
        service_phrase: str | None = None

        patterns = [
            r"(?:book|schedule|reserve)\s+(?:(?:a|an|the|my)\s+)?(?P<service>.+?)\s+at\s+",
            r"(?:i want|i need|i would like|looking for)\s+(?P<service>.+?)(?:\s+at\s+|\s+on\s+|\s+tomorrow|\s+today|\s+\d)",
            r"^(?P<service>(?:[A-Za-z]+\s+)*[A-Za-z]+)\s+(?:on|at)\s+",
        ]
        for pattern in patterns:
            match = re.search(pattern, source, re.IGNORECASE)
            if not match:
                continue
            service_phrase = match.group("service").strip(" .,-")
            break

        if not service_phrase and self._has_service_keyword(source):
            service_phrase = self._strip_booking_fillers(source)
            service_phrase = re.sub(r"\s+at\s+.+$", "", service_phrase, flags=re.IGNORECASE).strip()
            service_phrase = re.sub(r"\s+on\s+.+$", "", service_phrase, flags=re.IGNORECASE).strip()
            service_phrase = re.sub(r"\s+tomorrow.*$", "", service_phrase, flags=re.IGNORECASE).strip()

        if not service_phrase:
            return None

        service, category, confident = self.normalize_service_and_category(service_phrase)
        if confident and service:
            return service

        cleaned = self._strip_booking_fillers(service_phrase)
        if cleaned and self._is_plausible_service(cleaned):
            return title_case_safe(cleaned)
        return None

    def extract_date_and_time(self, text: str, current: BookingPayload) -> BookingPayload:
        payload = current.model_copy(deep=True)

        relative = self.extract_relative_date(text)
        if relative:
            payload.date = relative

        # Full date with year
        date_patterns = [
            r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b",
            r"\b(\d{4}-\d{2}-\d{2})\b",
            r"\bon(\d{1,2}/\d{1,2}/\d{4})\b",
            r"\bon\s*(\d{1,2}/\d{1,2}/\d{4})\b",
            r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                payload.date = match.group(1).strip()
                break
        else:
            # "25 July" without year — infer year (roll forward if already past)
            match = re.search(
                r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\b",
                text,
                re.IGNORECASE,
            )
            if match:
                parsed = self.parse_date(match.group(0))
                if parsed:
                    payload.date = self.format_display_date(parsed)

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
            _, category, confident = self.normalize_service_and_category(service)
            if not category:
                _, category, _ = self.normalize_service_and_category(text)
            if category:
                payload.category = category
            elif confident:
                mapped = self.category_agent.map_category(service, self.categories)
                if mapped:
                    payload.category = mapped

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
        elif not self._is_plausible_service(payload.service):
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
