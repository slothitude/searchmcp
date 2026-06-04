"""SearchMCP configuration — env vars, defaults, TTLs, domain authority."""

import os

# SearXNG — multiple backends for VPN fan-out
SEARXNG_URLS = {
    url.strip().split("=")[0]: url.strip().split("=", 1)[1]
    for url in os.environ.get(
        "SEARXNG_URLS",
        "nl=http://192.168.0.33:8899,us=http://192.168.0.33:8898,sg=http://192.168.0.33:8897"
    ).split(",")
    if url.strip() and "=" in url
}
# Backward compat — first URL as default
SEARXNG_URL = os.environ.get("SEARXNG_URL", list(SEARXNG_URLS.values())[0])

# Browser fallback (None = disabled)
BROWSER_CDP_URL = os.environ.get("BROWSER_CDP_URL")

# Cache
CACHE_DIR = os.environ.get("SEARCHMCP_CACHE_DIR", os.path.expanduser("~/.searchmcp"))

# Rate limiting
RATE_LIMIT = float(os.environ.get("SEARCHMCP_RATE_LIMIT", "2"))  # req/s per domain

# Concurrency
FETCH_CONCURRENCY = int(os.environ.get("SEARCHMCP_FETCH_CONCURRENCY", "5"))

# User agent
USER_AGENT = os.environ.get(
    "SEARCHMCP_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)

# HTTP timeouts
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0

# Cache TTLs and limits per content type
CACHE_CONFIG = {
    "search_results": {"ttl": 600, "max_entries": 200},    # 10 min
    "extracted":      {"ttl": 7200, "max_entries": 1000},   # 2 hours
    "browser":        {"ttl": 14400, "max_entries": 50},     # 4 hours
    "sitemap":        {"ttl": 86400, "max_entries": 20},     # 24 hours
}

# Domain authority scores (0.0–1.0) for search result ranking
DOMAIN_AUTHORITY = {
    "wikipedia.org": 0.95, "en.wikipedia.org": 0.95,
    "github.com": 0.92, "stackoverflow.com": 0.92,
    "developer.mozilla.org": 0.90, "mdn.io": 0.85,
    "arxiv.org": 0.88, "docs.python.org": 0.87,
    "pytorch.org": 0.85, "huggingface.co": 0.85,
    "npmjs.com": 0.84, "pypi.org": 0.84,
    "reddit.com": 0.75, "news.ycombinator.com": 0.80,
    "medium.com": 0.70, "dev.to": 0.72,
    "bbc.com": 0.82, "nytimes.com": 0.82, "reuters.com": 0.83,
    "theguardian.com": 0.80, "apnews.com": 0.82,
    "nature.com": 0.90, "science.org": 0.89,
    "youtube.com": 0.70, "x.com": 0.65, "twitter.com": 0.65,
    "linkedin.com": 0.68,
    "docs.rs": 0.87, "crates.io": 0.80,
    "rust-lang.org": 0.86,
    "go.dev": 0.86, "golang.org": 0.86,
    "typescriptlang.org": 0.86,
    "nextjs.org": 0.84, "react.dev": 0.84, "vuejs.org": 0.84,
    "fastapi.tiangolo.com": 0.83,
    "flask.palletsprojects.com": 0.83,
    "realpython.com": 0.78, "python.org": 0.85,
    "microsoft.com": 0.75, "learn.microsoft.com": 0.82,
    "aws.amazon.com": 0.80, "cloud.google.com": 0.80,
}

# Parameters to strip from URLs for cache key normalization
STRIP_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                "ref", "source", "fbclid", "gclid", "tab"}
