from __future__ import annotations

from app.utils.text import normalize_text, title_case_safe


def title_case_phrase(text: str) -> str:
    return title_case_safe(text.strip())


class CategoryAgent:
    """Map free-text service phrases to Bookly categories (orchestration only)."""

    KEYWORD_TO_CATEGORY = {
        "hair": "Hair",
        "haircut": "Hair",
        "hair cut": "Hair",
        "hair session": "Hair",
        "hair service": "Hair",
        "hair appointment": "Hair",
        "hair treatment": "Hair",
        "hair spa": "Hair",
        "hair styling": "Hair",
        "hair smooth": "Hair",
        "smoothing": "Hair",
        "smoothening": "Hair",
        "keratin": "Hair",
        "color": "Hair",
        "colour": "Hair",
        "coloring": "Hair",
        "colouring": "Hair",
        "bridal hair": "Hair",
        "makeup": "Makeup",
        "make up": "Makeup",
        "bridal makeup": "Makeup",
        "facial": "Face",
        "face": "Face",
        "face treatment": "Face",
        "skincare": "Face",
        "skin care": "Face",
        "nail": "Nails",
        "nails": "Nails",
        "nail service": "Nails",
        "manicure": "Nails",
        "pedicure": "Nails",
        "body": "Body",
        "body treatment": "Body",
        "massage": "Body",
        "spa": "Body",
        "bath": "Bath Treatment",
        "bath treatment": "Bath Treatment",
        "wax": "Hair Removal",
        "waxing": "Hair Removal",
        "hair removal": "Hair Removal",
        "threading": "Hair Removal",
        "henna": "Henna",
        "beard": "Grooming Services",
        "shave": "Grooming Services",
        "grooming": "Grooming Services",
    }

    CANONICAL_SERVICE_LABELS = {
        "hair smoothing": "Hair Smoothing",
        "hair smoothening": "Hair Smoothing",
        "hair spa": "Hair Spa",
        "hair styling": "Hair Styling",
        "hair treatment": "Hair Treatment",
        "hair session": "Hair",
        "hair service": "Hair",
        "hair appointment": "Hair",
        "hair cut": "Hair Cut",
        "hair coloring": "Hair Coloring",
        "hair colouring": "Hair Coloring",
        "keratin treatment": "Keratin Treatment",
        "keratin": "Keratin Treatment",
        "bridal makeup": "Bridal Makeup",
        "face treatment": "Face Treatment",
        "nail service": "Nails",
        "body treatment": "Body Treatment",
        "bath treatment": "Bath Treatment",
        "hair removal": "Hair Removal",
    }

    def map_category(self, service: str, known_categories: list[str]) -> str | None:
        service_n = normalize_text(service)
        for key, category in sorted(self.KEYWORD_TO_CATEGORY.items(), key=lambda x: -len(x[0])):
            if key in service_n and category in known_categories:
                return category

        for category in known_categories:
            if normalize_text(category) in service_n:
                return category
        return None

    def canonical_service_label(
        self, phrase: str, known_categories: list[str]
    ) -> tuple[str | None, str | None]:
        """Return (canonical_service, category) for a cleaned phrase."""
        text = normalize_text(phrase)
        if not text:
            return None, None

        for key, label in sorted(self.CANONICAL_SERVICE_LABELS.items(), key=lambda x: -len(x[0])):
            if text == key or text.startswith(f"{key} "):
                category = self.map_category(label, known_categories) or self.map_category(key, known_categories)
                return label, category

        category = self.map_category(text, known_categories)
        if category and text in self.KEYWORD_TO_CATEGORY:
            return category, category

        if category and len(text.split()) <= 3:
            return title_case_phrase(text), category

        return None, category
