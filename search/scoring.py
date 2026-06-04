"""Search result quality scoring and domain authority."""

import re
from urllib.parse import urlparse

from config import DOMAIN_AUTHORITY


def score_result(result: dict, query: str, time_range: str | None = None) -> float:
    """Score a search result for relevance and quality.

    Components:
    - Domain authority (built-in dict): weight 0.3
    - HTTPS + TLD bonus: weight 0.1
    - Snippet keyword relevance: weight 0.3
    - Title keyword relevance: weight 0.2
    - SearXNG engine score: weight 0.2
    - Freshness bonus for news queries: weight 0.2
    """
    score = 0.0

    # Domain authority
    domain = _get_base_domain(result.get("url", ""))
    auth = DOMAIN_AUTHORITY.get(domain, DOMAIN_AUTHORITY.get(_get_registered_domain(domain), 0.5))
    score += auth * 0.3

    # HTTPS + TLD bonus
    url = result.get("url", "")
    if url.startswith("https://"):
        score += 0.1
    parsed = urlparse(url)
    if parsed.hostname:
        tld = parsed.hostname.split(".")[-1].lower()
        if tld in ("org", "edu", "gov"):
            score += 0.05

    # Keyword relevance
    query_terms = set(re.findall(r'\b\w{3,}\b', query.lower()))
    query_terms -= {"the", "and", "for", "with", "this", "that"}

    snippet = result.get("snippet", "").lower()
    title = result.get("title", "").lower()

    if query_terms and snippet:
        snippet_hits = sum(1 for t in query_terms if t in snippet)
        score += 0.3 * (snippet_hits / len(query_terms))

    if query_terms and title:
        title_hits = sum(1 for t in query_terms if t in title)
        score += 0.2 * (title_hits / len(query_terms))

    # SearXNG engine score
    engine_score = result.get("score", 0)
    if engine_score:
        score += min(0.2, engine_score * 0.01)

    # Freshness bonus for news queries
    if time_range and result.get("publishedDate"):
        score += 0.2

    return round(score, 4)


def _get_base_domain(url: str) -> str:
    """Extract the full hostname from a URL."""
    try:
        parsed = urlparse(url)
        return (parsed.hostname or "").lower()
    except Exception:
        return ""


def _get_registered_domain(hostname: str) -> str:
    """Try to get the registered domain (e.g., 'bbc.co.uk' from 'www.bbc.co.uk')."""
    # Simple heuristic: take last 2 parts for common ccTLDs
    # For most cases, just strip 'www.'
    if hostname.startswith("www."):
        return hostname[4:]
    parts = hostname.split(".")
    if len(parts) >= 3 and parts[-1] in ("co", "com", "org", "gov", "edu", "net"):
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname
