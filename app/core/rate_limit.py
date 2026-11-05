"""按域名的间隔限速。锁里只占下一个时间槽，等待放在锁外。"""
import asyncio
import time
from urllib.parse import urlparse

from app.core.config import settings


class DomainRateLimiter:
    def __init__(self, rate_per_sec: float) -> None:
        self.rate = rate_per_sec
        self._next: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, url: str) -> None:
        domain = urlparse(url).netloc
        if not domain or self.rate <= 0:
            return
        interval = 1.0 / self.rate
        async with self._lock:
            now = time.monotonic()
            nxt = self._next.get(domain, 0.0)
            if now >= nxt:
                scheduled = now
                self._next[domain] = now + interval
            else:
                scheduled = nxt
                self._next[domain] = nxt + interval
            self._prune(now)
        wait = scheduled - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)

    def _prune(self, now: float) -> None:
        if len(self._next) <= 256:
            return
        cutoff = now - 60.0
        stale = [host for host, nxt in self._next.items() if nxt < cutoff]
        for host in stale:
            del self._next[host]


def catalog_extra_wait(delay: float, rate_per_sec: float) -> float:
    """delay 是页面最小间隔。限速已经等待过的部分不再叠加。"""
    if delay <= 0:
        return 0.0
    if rate_per_sec <= 0:
        return delay
    return max(0.0, delay - (1.0 / rate_per_sec))


rate_limiter = DomainRateLimiter(settings.RATE_LIMIT_PER_DOMAIN)
