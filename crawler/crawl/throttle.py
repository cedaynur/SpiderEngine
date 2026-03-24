"""Back-pressure and rate limiting for crawl workers."""

from __future__ import annotations

import threading
import time
from typing import Any


class BackPressureController:
    """Signals throttling state for UI and worker coordination."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._throttled = False
        self._message = ""

    def acquire_slot(self) -> None:
        pass

    def release_slot(self) -> None:
        pass

    def is_throttled(self):
        with self._lock:
            return self._throttled

    def status_message(self):
        with self._lock:
            return self._message

    def set_throttled(self, active: bool, message: str = "") -> None:
        with self._lock:
            self._throttled = active
            self._message = message


class RateLimiter:
    """
    Enforces a minimum interval between successive operations (e.g. HTTP fetches).

    Uses a :class:`threading.Lock` so all workers share one global spacing, which
    reduces burst load on targets and on the local machine (PRD back-pressure).

    If ``metrics_monitor`` is set, it is notified while a worker sleeps for rate
    limiting so UIs can show ``THROTTLED`` (see :class:`crawler.metrics.MetricsMonitor`).
    """

    def __init__(self, delay_sec: float, metrics_monitor: Any | None = None) -> None:
        self._delay_sec = max(0.0, delay_sec)
        self._lock = threading.Lock()
        self._last_end: float | None = None
        self._metrics = metrics_monitor

    def wait_if_needed(self) -> None:
        """Block until at least ``delay_sec`` has passed since the previous call."""
        if self._delay_sec <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if self._last_end is not None:
                wait = self._delay_sec - (now - self._last_end)
                if wait > 0:
                    if self._metrics is not None and hasattr(
                        self._metrics, "set_rate_limited"
                    ):
                        self._metrics.set_rate_limited(True)
                    try:
                        time.sleep(wait)
                    finally:
                        if self._metrics is not None and hasattr(
                            self._metrics, "set_rate_limited"
                        ):
                            self._metrics.set_rate_limited(False)
                    now = time.monotonic()
            self._last_end = now
