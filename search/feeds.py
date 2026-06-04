"""Sitemap and RSS/Atom feed parsing with autodiscovery."""

import logging
import re
from urllib.parse import urlparse, urljoin

import httpx

from config import USER_AGENT, CONNECT_TIMEOUT

logger = logging.getLogger(__name__)


async def read_sitemap(url: str, pattern: str = "", limit: int = 100) -> list[str]:
    """Discover URLs from a sitemap or RSS/Atom feed.

    Autodiscovery chain:
    1. Try the provided URL directly
    2. If 404, try {root}/sitemap.xml
    3. If still 404, try {root}/robots.txt → parse Sitemap: directive
    4. If still nothing, try {root}/feed and {root}/rss
    """
    async with httpx.AsyncClient(
        timeout=15.0,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:

        # 1. Try direct URL
        urls = await _try_url(client, url, pattern, limit)
        if urls:
            return urls

        # Build root URL
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"

        # 2. Try /sitemap.xml
        sitemap_url = f"{root}/sitemap.xml"
        if sitemap_url != url:
            urls = await _try_url(client, sitemap_url, pattern, limit)
            if urls:
                return urls

        # 3. Try robots.txt → Sitemap: directive
        try:
            resp = await client.get(f"{root}/robots.txt")
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemap_from_robots = line.split(":", 1)[1].strip()
                        urls = await _try_url(client, sitemap_from_robots, pattern, limit)
                        if urls:
                            return urls
        except Exception:
            pass

        # 4. Try common feed paths
        for feed_path in ["/feed", "/rss", "/atom.xml"]:
            feed_url = f"{root}{feed_path}"
            if feed_url != url:
                urls = await _try_url(client, feed_url, pattern, limit)
                if urls:
                    return urls

    return []


async def _try_url(client: httpx.AsyncClient, url: str, pattern: str,
                  limit: int) -> list[str]:
    """Try to parse a URL as sitemap, RSS, or Atom feed."""
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return []

        content_type = resp.headers.get("content-type", "")
        text = resp.text[:500000]  # Cap at 500KB

        # Detect format from content
        if "<sitemapindex" in text or "<urlset" in text:
            return _parse_xml_sitemap(text, pattern, limit)
        if "<rss" in text or "<feed" in text:
            return _parse_rss_atom(text, url, pattern, limit)

        # Try XML parsing regardless
        if "<" in text[:10]:
            return _parse_xml_sitemap(text, pattern, limit) or _parse_rss_atom(text, url, pattern, limit)

    except Exception as e:
        logger.debug(f"Feed parsing failed for {url}: {e}")

    return []


def _parse_xml_sitemap(text: str, pattern: str, limit: int) -> list[str]:
    """Parse XML sitemap (sitemapindex or urlset)."""
    import re as regex

    urls = []

    # URL entries
    for match in regex.finditer(r'<loc>\s*(.*?)\s*</loc>', text):
        url = match.group(1).strip()
        if _matches_pattern(url, pattern):
            urls.append(url)
        if len(urls) >= limit:
            return urls

    # Sitemap index entries (recurse is handled by returning the sitemap URLs)
    if not urls:
        for match in regex.finditer(r'<sitemap>\s*<loc>\s*(.*?)\s*</loc>', text, regex.DOTALL):
            url = match.group(1).strip()
            if _matches_pattern(url, pattern):
                urls.append(url)
            if len(urls) >= limit:
                return urls

    return urls


def _parse_rss_atom(text: str, base_url: str, pattern: str, limit: int) -> list[str]:
    """Parse RSS or Atom feed entries."""
    import feedparser

    feed = feedparser.parse(text)
    urls = []

    for entry in feed.entries:
        url = entry.get("link") or entry.get("id", "")
        if not url:
            continue
        # Resolve relative URLs
        if url.startswith("/"):
            url = urljoin(base_url, url)
        if _matches_pattern(url, pattern):
            urls.append(url)
        if len(urls) >= limit:
            break

    return urls


def _matches_pattern(url: str, pattern: str) -> bool:
    """Check if a URL matches a regex pattern."""
    if not pattern:
        return True
    try:
        return bool(re.search(pattern, url))
    except re.error:
        return True
