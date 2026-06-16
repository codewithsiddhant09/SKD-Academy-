from __future__ import annotations

import time
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._value: T | None = None
        self._expires_at = 0.0
        self._lock = Lock()

    def get(self) -> T | None:
        with self._lock:
            if self._value is None or time.time() >= self._expires_at:
                return None
            return self._value

    def set(self, value: T) -> None:
        with self._lock:
            self._value = value
            self._expires_at = time.time() + self.ttl_seconds

    def has_value(self) -> bool:
        return self.get() is not None
