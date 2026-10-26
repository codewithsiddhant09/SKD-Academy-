from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AuthService:
    def login(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        settings = get_settings()
        try:
            with httpx.Client(timeout=settings.booking_api_timeout_seconds, verify=settings.booking_api_verify_ssl) as client:
                response = client.post(settings.login_api_url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Bookly login timed out. Please try again.") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 401}:
                raise RuntimeError("Bookly rejected the login credentials.") from exc
            logger.warning("BOOKLY_LOGIN_HTTP_FAILED: status=%s", exc.response.status_code)
            raise RuntimeError(f"Bookly login API returned HTTP {exc.response.status_code}.") from exc
        except httpx.RequestError as exc:
            logger.warning("BOOKLY_LOGIN_REQUEST_FAILED: %s", type(exc).__name__)
            raise RuntimeError("Bookly login service is unavailable.") from exc
        except ValueError as exc:
            raise RuntimeError("Bookly login API returned invalid JSON.") from exc

        if not isinstance(result, dict) or result.get("error") is True:
            raise RuntimeError("Bookly rejected the login credentials.")
        if result.get("success") is False:
            raise RuntimeError("Bookly rejected the login credentials.")
        if isinstance(result.get("results"), dict) and result["results"].get("user") is False:
            raise RuntimeError("Bookly rejected the login credentials.")
        token = self._find_value(result, {"token", "accessToken", "access_token", "authToken", "auth_token"})
        user_id = self._find_value(result, {"userId", "user_id", "_id", "id"})
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("Bookly login response did not contain an authentication token.")
        if not user_id:
            raise RuntimeError("Bookly login response did not contain a user ID.")
        return {"token": token.strip(), "user_id": str(user_id)}

    @classmethod
    def _find_value(cls, value: Any, keys: set[str]) -> Any:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys and item is not None:
                    return item
            for item in value.values():
                found = cls._find_value(item, keys)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = cls._find_value(item, keys)
                if found is not None:
                    return found
        return None
