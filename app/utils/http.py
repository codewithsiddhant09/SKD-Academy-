from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.config import get_settings


@retry(stop=stop_after_attempt(3), wait=wait_fixed(0.5), reraise=True)
def get_json(url: str) -> list[dict] | dict:
    settings = get_settings()
    with httpx.Client(timeout=settings.request_timeout_seconds, verify=settings.verify_ssl) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()
