"""A small in-process rate limit, for the requests that make Previewit do work for strangers:
checking web pages (ADR 0022) and preparing review requests for AI assistants (ADR 0023).

Each worker counts on its own, so with several workers the real limit is a few times higher.
That is enough to stop a script hammering one worker; a site-wide limit belongs in nginx.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable


class RateLimiter:
    """At most `count` events per `seconds` for each key."""

    def __init__(
        self,
        count: int,
        seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self._count = count
        self._seconds = seconds
        self._clock = clock
        self._max_keys = max_keys
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            events = self._events.setdefault(key, deque())
            self._events.move_to_end(key)
            while events and now - events[0] >= self._seconds:
                events.popleft()
            if len(events) >= self._count:
                return False
            events.append(now)
            while len(self._events) > self._max_keys:
                self._events.popitem(last=False)
            return True
