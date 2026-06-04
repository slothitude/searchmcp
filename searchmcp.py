"""SearchMCP — Agent-First Search and Web Reading MCP Server.

Three-tier extraction: trafilatura (fast) → trafilatura precision retry →
crawl4ai browser fallback → BeautifulSoup last resort.

Search: SearXNG + quality scoring + smart dedup + parallel fetch.
Cache: aiosqlite-backed, count-based LRU with stampede protection.
Rate limiting: per-domain token bucket + robots.txt cache.
"""

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastmcp import FastMCP

from config import (SEARXNG_URL, SEARXNG_URLS, BROWSER_CDP_URL, CACHE_DIR,
                    USER_AGENT, CONNECT_TIMEOUT, READ_TIMEOUT)
from cache import store as cache_store
from utils.urls import normalize_url, extract_domain
from utils.rate_limit import acquire, robots
from utils.markdown import make_error_block
from extract.quality import has_article_body, is_js_heavy
from extract.tier1 import extract_broad, extract_precision, extract_metadata
from extract.tier3 import extract_browser, extract_beautifulsoup
from extract.postprocess import postprocess
from extract.summarize import summarize
from search.searxng import search as searxng_search, classify_query, search_and_extract
from search.feeds import read_sitemap as parse_feeds

# ─── Lifecycle ───

@asynccontextmanager
async def lifespan(app):
    await cache_store.init()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    yield
    await cache_store.close()


mcp = FastMCP("searchmcp", instructions="Agent-optimized search and web reading. Returns clean markdown with metadata.", lifespan=lifespan)


# ─── Core extraction (used by multiple tools) ───

async def _fetch_html(url: str) -> tuple[str | None, str]:
    """Fetch HTML from a URL. Returns (html, error_type)."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text, ""
    except httpx.TimeoutException:
        return None, "timeout_error"
    except httpx.HTTPStatusError as e:
        return None, "http_error"
    except Exception:
        return None, "fetch_error"


async def _extract_content(url: str, max_length: int = 50000,
                           include_metadata: bool = True,
                           use_browser: bool = False,
                           no_cache: bool = False) -> str:
    """Full extraction pipeline for a single URL.

    Checks robots.txt → rate limit → cache → HTTP fetch → tiered extraction → post-process.
    """
    cache_key = normalize_url(url)

    # Check cache
    if not no_cache:
        cached = await cache_store.get(cache_key)
        if cached:
            return cached["content"]

    # Check robots.txt
    if not await robots.can_fetch(url):
        return make_error_block("robots_blocked", url)

    # Rate limit
    domain = extract_domain(url)
    await acquire(domain)

    # Fetch HTML
    html, error_type = await _fetch_html(url)
    if error_type == "timeout_error":
        return make_error_block("timeout_error", url)
    if error_type == "http_error":
        return make_error_block("http_error", url, message="HTTP error")
    if error_type == "fetch_error":
        return make_error_block("fetch_error", url, message="Network error")

    html_len = len(html)

    # Tier 1: trafilatura broad recall
    result = extract_broad(html, url)
    text = result.get("text", "")

    # Quality check → Tier 2: trafilatura precision
    if not has_article_body(text, html_len):
        result = extract_precision(html, url)
        text = result.get("text", "")

    # Tier 3: browser fallback if JS-heavy or requested
    if not has_article_body(text, html_len) and (
        use_browser or is_js_heavy(text, html_len)
    ):
        browser_result = await extract_browser(url, BROWSER_CDP_URL)
        if browser_result.get("success"):
            text = browser_result["text"]

    # Last resort: BeautifulSoup
    if not text or len(text) < 50:
        bs_result = extract_beautifulsoup(html, url)
        if bs_result.get("success"):
            text = bs_result["text"]

    # Determine content type for cache
    content_type = "browser" if use_browser and is_js_heavy(text, html_len) else "extracted"

    # Post-process
    output = postprocess(text, url, html, max_length, include_metadata)

    # Cache (don't cache errors)
    if not output.startswith("<!-- meta\nstatus: error"):
        meta = extract_metadata(html, url)
        await cache_store.put(cache_key, url, output, content_type, metadata=meta)

    return output


# ─── MCP Tools ───

@mcp.tool()
async def search(
    query: str,
    category: str = "general",
    max_results: int = 10,
    time_range: Optional[str] = None,
    language: str = "en",
    location: str = "all",
) -> str:
    """Search the web via SearXNG. Returns ranked, deduplicated results as markdown.
    location: 'all' (parallel fan-out to all backends), 'nl', 'us', 'sg', or any configured key."""
    classification = classify_query(query)
    effective_category = category if category != "general" else classification["categories"]
    effective_time_range = time_range or classification.get("time_range")

    results = await searxng_search(
        query,
        categories=effective_category,
        language=language,
        max_results=max_results,
        time_range=effective_time_range,
        location=location,
    )

    if not results:
        return make_error_block("search_error", url=f"query:{query}",
                               message="No results found")

    lines = [f"## Search: {query}\n"]
    for i, r in enumerate(results, 1):
        score = r.get("quality_score", 0)
        snippet = r.get("snippet", "")
        lines.append(f"{i}. [{r['title']}]({r['url']})")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append(f"   (score: {score:.2f})")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def search_and_read(
    query: str,
    max_results: int = 3,
    max_length: int = 6000,
    return_errors: bool = False,
    location: str = "all",
) -> str:
    """Search the web and read top results concurrently. Returns combined markdown.
    location: 'all' (parallel fan-out), 'nl', 'us', 'sg'."""
    return await search_and_extract(
        query,
        extract_fn=_extract_content,
        max_results=max_results,
        max_length=max_length,
        return_errors=return_errors,
        location=location,
    )


@mcp.tool()
async def read_url(
    url: str,
    format: str = "md",
    max_length: int = 50000,
    include_metadata: bool = True,
    use_browser: bool = False,
    no_cache: bool = False,
) -> str:
    """Extract content from a URL. Returns clean markdown with metadata header."""
    return await _extract_content(
        url,
        max_length=max_length,
        include_metadata=include_metadata,
        use_browser=use_browser,
        no_cache=no_cache,
    )


@mcp.tool()
async def read_urls(
    urls: list[str],
    max_length: int = 6000,
    max_concurrency: int = 5,
    return_errors: bool = False,
) -> str:
    """Batch read multiple URLs in parallel. Returns combined markdown."""
    from config import FETCH_CONCURRENCY

    semaphore = asyncio.Semaphore(min(max_concurrency, FETCH_CONCURRENCY))

    async def fetch_one(url: str) -> tuple[str, str, str]:
        async with semaphore:
            try:
                content = await _extract_content(url, max_length=max_length)
                return (url, content, "")
            except Exception as e:
                return (url, "", str(e))

    tasks = [fetch_one(u) for u in urls]
    results = await asyncio.gather(*tasks)

    parts = []
    for url, content, error in results:
        if not content and error:
            if return_errors:
                parts.append(f"### {url}\nError: {error}\n")
            continue
        parts.append(content)
        parts.append("")

    return "\n".join(parts)


@mcp.tool()
async def read_sitemap(
    url: str,
    pattern: str = "",
    limit: int = 100,
) -> str:
    """Discover URLs from a sitemap, RSS, or Atom feed. Autodiscovers if URL is a root domain."""
    try:
        urls = await parse_feeds(url, pattern, limit)
    except Exception as e:
        return make_error_block("fetch_error", url, message=str(e))

    if not urls:
        return f"No URLs found for {url}"

    lines = [f"## URLs from {url}\n"]
    for i, u in enumerate(urls, 1):
        lines.append(f"{i}. {u}")

    return "\n".join(lines)


@mcp.tool()
async def extract(
    url: str,
    fields: list[dict],
    multiple: bool = False,
) -> str:
    """Extract specific fields from a URL using CSS selectors.

    Fields: [{"name": "title", "selector": "h1", "attr": "text"}]
    attr can be "text" for text content or any HTML attribute name.
    """
    cache_key = normalize_url(url)
    cached = await cache_store.get(cache_key)
    if cached:
        html, error = await _fetch_html(url)
        if error:
            return make_error_block(error, url)
    else:
        html, error = await _fetch_html(url)
        if error:
            return make_error_block(error, url)

    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        from bs4 import BeautifulSoup as BS
        soup = BS(html, "html.parser")

    results = {}
    for field in fields:
        name = field.get("name", "unknown")
        selector = field.get("selector", "")
        attr = field.get("attr", "text")

        elements = soup.select(selector)

        if not elements:
            results[name] = None
            continue

        if multiple:
            values = []
            for el in elements:
                values.append(_get_attr(el, attr))
            results[name] = values
        else:
            results[name] = _get_attr(elements[0], attr)

    return f"## Extracted from {url}\n\n```json\n{json.dumps(results, indent=2, ensure_ascii=False)}\n```"


def _get_attr(element, attr: str) -> str | None:
    """Get an attribute or text content from a BeautifulSoup element."""
    if attr == "text":
        return element.get_text(strip=True) or None
    return element.get(attr) or None


@mcp.tool()
async def summarize_content(
    url: str,
    max_sentences: int = 10,
    style: str = "bullets",
) -> str:
    """Extract key sentences from a URL's content (no LLM, extractive scoring)."""
    content = await _extract_content(url, max_length=50000, include_metadata=False)

    # Strip metadata block if present
    if content.startswith("<!-- meta"):
        end = content.find("-->") + 3
        content = content[end:].strip()

    # Strip markdown headings for summarization
    import re
    content = re.sub(r"^#{1,6}\s.*$", "", content, flags=re.MULTILINE).strip()

    if not content:
        return make_error_block("extraction_error", url, message="No content to summarize")

    title = ""
    # Try to extract title from metadata cache
    cache_key = normalize_url(url)
    cached = await cache_store.get(cache_key)
    if cached and cached.get("metadata"):
        title = cached["metadata"].get("title", "")

    summary = summarize(content, max_sentences=max_sentences, style=style, title=title)

    if not summary:
        return make_error_block("extraction_error", url, message="Summarization failed")

    return f"## Summary: {url}\n\n{summary}"


@mcp.tool()
async def cache_status() -> str:
    """Show cache statistics — entry counts per type, limits, TTLs."""
    stats = await cache_store.stats()
    return f"## Cache Status\n\n```json\n{json.dumps(stats, indent=2)}\n```"


@mcp.tool()
async def clear_cache(url: str = "") -> str:
    """Clear cache entries. Provide a URL to clear one entry, or omit to clear all."""
    if url:
        key = normalize_url(url)
        deleted = await cache_store.clear(key)
        return f"Cleared cache entry for {url}" if deleted else f"No cache entry for {url}"
    else:
        deleted = await cache_store.clear()
        return f"Cleared all cache entries ({deleted} removed)"


# ─── Main ───

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SearchMCP Server")
    parser.add_argument("--log-level", default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--port", type=int, default=8012, help="SSE port (default: 8012)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), stream=sys.stderr)
    mcp.run(transport="sse", host=args.host, port=args.port)
