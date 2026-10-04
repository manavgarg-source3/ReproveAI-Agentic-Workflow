"""
Thread-safe rate limiter and polite backoff coordinator for external APIs.
Prevents HTTP 429 Too Many Requests across concurrent threads.
"""
import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PoliteRateLimiter:
    """
    Thread-safe pacing limiter and shared backoff manager.
    Ensures that concurrent threads space their requests and collectively
    pause when an API returns HTTP 429.
    """

    def __init__(self, name: str, min_interval_seconds: float = 0.35, default_backoff_seconds: float = 5.0):
        self.name = name
        self.min_interval = min_interval_seconds
        self.default_backoff = default_backoff_seconds
        self._lock = threading.Lock()
        self._last_request_time = 0.0
        self._backoff_until = 0.0

    def acquire(self) -> None:
        """
        Blocks until the rate limit permit is available and any global backoff has cleared.
        """
        while True:
            with self._lock:
                now = time.time()
                # 1. Check if we are in a global 429 backoff
                if now < self._backoff_until:
                    sleep_needed = self._backoff_until - now
                else:
                    sleep_needed = 0.0
                    # 2. Check pacing between requests
                    elapsed = now - self._last_request_time
                    if elapsed < self.min_interval:
                        sleep_needed = self.min_interval - elapsed

                if sleep_needed <= 0.001:
                    self._last_request_time = time.time()
                    return

            # Sleep outside the lock so other threads can evaluate status
            time.sleep(min(sleep_needed, 2.0))

    def trigger_backoff(self, retry_after_header: Optional[str] = None, attempt: int = 1) -> float:
        """
        Called when HTTP 429 occurs. Sets a global backoff window for all threads.
        """
        with self._lock:
            backoff_duration = self.default_backoff * (1.5 ** (attempt - 1))
            if retry_after_header and retry_after_header.strip().isdigit():
                backoff_duration = max(float(retry_after_header) + 1.0, backoff_duration)
            
            now = time.time()
            self._backoff_until = max(self._backoff_until, now + backoff_duration)
            logger.warning(
                f"[{self.name}] Rate limit (HTTP 429) active. Pausing all threads for {backoff_duration:.1f}s..."
            )
            return backoff_duration

    def is_in_backoff(self) -> bool:
        """Returns True if the provider is currently cooling down after a 429."""
        return time.time() < self._backoff_until

