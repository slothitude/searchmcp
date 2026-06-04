"""SearXNG search client with query classification and parallel fan-out."""

import asyncio
import logging
import re

import httpx

from config import SEARXNG_URLS, USER_AGENT, READ_TIMEOUT, FETCH_CONCURRENCY
from search.scoring import score_result
from search.dedup import deduplicate

logger = logging.getLogger(__name__)

# Time range mapping for SearXNG
_TIME_RANGE_MAP = {
    "day": "day",
    "week": "week",
    "month": "month",
    "year": "year",
    "news": "week",
}


def classify_query(query: str) -> dict:
    """Classify a search query to optimize SearXNG parameters (heuristic, no LLM).

    Extended from alphabetty/core/searxng.py with shopping, social, and reference patterns.
    """
    q = query.lower()

    # News / recent events
    if any(w in q for w in ("latest", "news", "recent", "today", "this week",
                             "breaking", "update", "current events", "headline",
                             "yesterday", "just announced")):
        return {"categories": "news", "time_range": "week"}

    # Technical / how-to
    if any(w in q for w in ("how to", "tutorial", "install", "setup", "configure",
                             "guide", "example", "debug", "fix", "error", "issue",
                             "troubleshoot", "cli", "api")):
        return {"categories": "it", "time_range": None}

    # Academic / research
    if any(w in q for w in ("paper", "research", "study", "arxiv", "journal",
                             "publication", "citation", "doi", "survey",
                             "systematic review", "meta-analysis")):
        return {"categories": "science", "time_range": "year"}

    # Science
    if any(w in q for w in ("formula", "equation", "theorem", "proof", "algorithm",
                             "experiment", "hypothesis", "theory", "physics",
                             "chemistry", "biology")):
        return {"categories": "science", "time_range": None}

    # Shopping / products
    if any(w in q for w in ("buy", "price", "cheap", "best", "review", "vs",
                             "versus", "comparison", "deal", "discount")):
        return {"categories": "general", "time_range": None}

    # Social / forums
    if any(w in q for w in ("reddit", "twitter", "discussion", "thread", "opinion",
                             "people say", "controversy")):
        return {"categories": "general", "time_range": "month"}

    # Reference / documentation
    if any(w in q for w in ("documentation", "docs", "reference", "specification",
                             "standard", "rfc", "man page")):
        return {"categories": "it", "time_range": None}

    # Files / downloads
    if any(w in q for w in ("download", "github", "release", "binary", "package")):
        return {"categories": "it", "time_range": None}

    # Images / videos
    if any(w in q for w in ("image", "photo", "picture", "video", "watch")):
        return {"categories": "images", "time_range": None}

    return {"categories": "general", "time_range": None}


async def _search_one(url: str, params: dict) -> list[dict]:
    """Search a single SearXNG backend. Returns parsed results or empty list."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(READ_TIMEOUT),
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(f"{url}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "engine": item.get("engine", ""),
                "score": item.get("score", 0),
                "category": item.get("category", ""),
                "publishedDate": item.get("publishedDate"),
            })
        return results
    except Exception as e:
        logger.warning(f"SearXNG {url} failed: {e}")
        return []


async def search(query: str, categories: str = "general", language: str = "en",
                 max_results: int = 10, time_range: str | None = None,
                 location: str = "all") -> list[dict]:
    """Search via SearXNG with parallel fan-out to multiple VPN backends.

    location: 'all' (parallel fan-out to all backends), 'nl', 'us', 'sg',
              or any key in SEARXNG_URLS.
    """
    params = {
        "q": query,
        "format": "json",
        "categories": categories,
        "language": language,
    }
    if time_range:
        params["time_range"] = _TIME_RANGE_MAP.get(time_range, time_range)

    # Select backends
    if location == "all":
        urls = list(SEARXNG_URLS.values())
    elif location in SEARXNG_URLS:
        urls = [SEARXNG_URLS[location]]
    else:
        urls = list(SEARXNG_URLS.values())

    # Fan out to all selected backends in parallel
    tasks = [_search_one(url, params) for url in urls]
    all_raw = await asyncio.gather(*tasks)
    raw_results = []
    for results in all_raw:
        raw_results.extend(results)

    if not raw_results:
        return []

    # Score results
    for result in raw_results:
        result["quality_score"] = score_result(result, query, time_range)

    # Sort by quality score
    raw_results.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

    # Deduplicate
    results = deduplicate(raw_results)

    # Trim to max_results
    return results[:max_results]


async def search_and_extract(query: str, extract_fn, max_results: int = 3,
                             max_length: int = 6000, return_errors: bool = False,
                             time_range: str | None = None,
                             location: str = "all") -> str:
    """Search SearXNG, then extract content from top N results concurrently.

    extract_fn is an async callable: extract_fn(url, max_length) -> str
    location: 'all' (parallel fan-out), or a specific backend key.
    """
    classification = classify_query(query)
    effective_time_range = time_range or classification.get("time_range")

    results = await search(
        query,
        categories=classification["categories"],
        max_results=max_results,
        time_range=effective_time_range,
        location=location,
    )

    if not results:
        return _format_search_error(query)

    # Fetch top results concurrently
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def fetch_one(result: dict) -> dict:
        async with semaphore:
            url = result["url"]
            try:
                content = await extract_fn(url, max_length)
                return {"url": url, "title": result["title"], "content": content, "error": None}
            except Exception as e:
                if return_errors:
                    return {"url": url, "title": result["title"],
                            "content": f"Extraction failed: {e}", "error": str(e)}
                return None

    tasks = [fetch_one(r) for r in results]
    fetched = await asyncio.gather(*tasks)

    # Format output
    parts = [f"## Search: {query}\n"]
    for item in fetched:
        if item is None:
            continue
        parts.append(f"### [{item['title']}]({item['url']})\n")
        parts.append(item["content"])
        parts.append("")

    return "\n".join(parts)


def _format_search_error(query: str) -> str:
    return f"<!-- meta\nstatus: error\nerror_type: search_error\n-->\nNo results found for: {query}"
