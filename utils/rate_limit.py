"""Per-domain rate limiting and robots.txt caching."""

import asyncio
import logging
import time
import urllib.robotparser
from collections import defaultdict

import httpx

from config import RATE_LIMIT, USER_AGENT, CONNECT_TIMEOUT

logger = logging.getLogger(__name__)

# Token bucket per domain
_buckets: dict[str, dict] = defaultdict(lambda: {"tokens": RATE_LIMIT, "last_refill": time.time()})
_lock = asyncio.Lock()


async def acquire(domain: str) -> None:
    """Wait until a token is available for the given domain."""
    async with _lock:
        now = time.time()
        bucket = _buckets[domain]
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(RATE_LIMIT, bucket["tokens"] + elapsed * RATE_LIMIT)
        bucket["last_refill"] = now

        if bucket["tokens"] < 1:
            wait_time = (1 - bucket["tokens"]) / RATE_LIMIT
            await asyncio.sleep(wait_time)
            bucket["tokens"] = 0
            bucket["last_refill"] = time.time()
        else:
            bucket["tokens"] -= 1


class RobotsCache:
    """Async robots.txt cache with TTL."""

    def __init__(self, ttl: float = 3600):
        self._cache: dict[str, tuple[float, urllib.robotparser.RobotFileParser]] = {}
        self._ttl = ttl

    def _get_parser(self, domain: str) -> urllib.robotparser.RobotFileParser | None:
        entry = self._cache.get(domain)
        if entry:
            ts, parser = entry
            if time.time() - ts < self._ttl:
                return parser
            del self._cache[domain]
        return None

    async def can_fetch(self, url: str) -> bool:
        """Check if robots.txt allows fetching this URL."""
        from utils.urls import extract_domain
        domain = extract_domain(url)
        parser = self._get_parser(domain)

        if parser is None:
            parser = await self._fetch_robots(domain, url)

        if parser is None:
            return True  # If we can't fetch robots.txt, allow

        return parser.can_fetch(USER_AGENT, url)

    async def _fetch_robots(self, domain: str, url: str) -> urllib.robotparser.RobotFileParser | None:
        try:
            scheme = "https" if "https" in url else "http"
            robots_url = f"{scheme}://{domain}/robots.txt"
            async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as client:
                resp = await client.get(robots_url, headers={"User-Agent": USER_AGENT},
                                        follow_redirects=True)
                if resp.status_code != 200:
                    return None
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(resp.text.splitlines())
            self._cache[domain] = (time.time(), parser)
            return parser
        except Exception:
            return None


# Global robots cache instance
robots = RobotsCache()
