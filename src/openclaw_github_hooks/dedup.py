"""In-memory TTL dedup keyed on the X-GitHub-Delivery header."""

import time


class DeliveryDedup:
    def __init__(self, ttl_seconds: float = 6 * 3600, max_entries: int = 10_000):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._seen: dict[str, float] = {}

    def seen_before(self, delivery_id: str) -> bool:
        """Record delivery_id; return True if it was already recorded."""
        now = time.monotonic()
        self._evict(now)
        if delivery_id in self._seen:
            return True
        self._seen[delivery_id] = now
        return False

    def _evict(self, now: float) -> None:
        expired = [k for k, t in self._seen.items() if now - t > self._ttl]
        for k in expired:
            del self._seen[k]
        if len(self._seen) >= self._max:
            oldest = sorted(self._seen, key=self._seen.get)[: self._max // 2]
            for k in oldest:
                del self._seen[k]
