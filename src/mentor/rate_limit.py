"""
A small in-memory limit on how often one caller may ask for a price.

One endpoint needs this and it is the one with no account behind it. The live
preview on the registration form is called while someone types, by anybody at
all, and every call scores a gradient-boosted model. Without a limit, a single
page left open in a loop is the whole server's capacity.

What this is, precisely, so it is not mistaken for something better: a
sliding window counted in this process's memory, keyed by the caller's
address. It resets when the server restarts, it counts nothing that reaches
another worker, and it is no defence at all against a flood from many
addresses. It is there so that one client cannot accidentally take the service
down, which is the failure that actually happens. A real deployment puts the
rate limit in front of the application, where it can see every worker.

The window is a sliding one rather than a fixed minute, because a fixed minute
lets twice the limit through across a boundary: sixty calls in the last second
of one minute and sixty in the first second of the next.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """
    How many calls one key may make in one window, and whether this is one.

    A dataclass rather than a module-level counter so a test can build one
    with a limit of three and a window of a second, instead of making sixty
    calls and waiting a minute to see the sixty-first refused.
    """

    limit: int
    window: float
    _calls: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(deque), repr=False
    )

    def allow(self, key: str, now: float | None = None) -> bool:
        """
        Whether this call is within the limit, counting it if it is.

        Calls older than the window are dropped first, which is also what
        keeps the memory bounded: a key that stops calling keeps at most one
        window's worth of timestamps until it is next seen.
        """
        moment = time.monotonic() if now is None else now
        calls = self._calls[key]
        while calls and calls[0] <= moment - self.window:
            calls.popleft()
        if len(calls) >= self.limit:
            return False
        calls.append(moment)
        return True

    def retry_after(self, key: str, now: float | None = None) -> int:
        """
        Whole seconds until the oldest counted call leaves the window.

        At least one, because a Retry-After of zero reads as "try again
        immediately", which is what the caller just did.
        """
        moment = time.monotonic() if now is None else now
        calls = self._calls.get(key)
        if not calls:
            return 1
        return max(1, int(round(self.window - (moment - calls[0]))))

    def forget(self) -> None:
        """Drop every counted call. For a test, and for a restart in effect."""
        self._calls.clear()
