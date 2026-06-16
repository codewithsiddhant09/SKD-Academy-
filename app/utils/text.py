import re


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def title_case_safe(value: str) -> str:
    return " ".join(part.capitalize() for part in normalize_text(value).split(" ") if part)
