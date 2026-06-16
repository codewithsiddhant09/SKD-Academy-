from __future__ import annotations

from app.utils.text import normalize_text


class CategoryAgent:
    KEYWORD_TO_CATEGORY = {
        "hair": "Hair",
        "smoothing": "Hair",
        "color": "Hair",
        "bridal makeup": "Makeup",
        "makeup": "Makeup",
        "facial": "Face",
        "wax": "Hair Removal",
        "hair removal": "Hair Removal",
        "pedicure": "Nails",
        "manicure": "Nails",
        "henna": "Henna",
        "bath": "Bath Treatment",
    }

    def map_category(self, service: str, known_categories: list[str]) -> str | None:
        service_n = normalize_text(service)
        for key, category in self.KEYWORD_TO_CATEGORY.items():
            if key in service_n and category in known_categories:
                return category

        for category in known_categories:
            if normalize_text(category) in service_n:
                return category
        return None
