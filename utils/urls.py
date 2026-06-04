"""URL normalization and domain extraction for cache keys."""

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from config import STRIP_PARAMS


def normalize_url(url: str) -> str:
    """Normalize a URL for use as a cache key.

    Strips UTM/tracking params, normalizes scheme+host to lowercase,
    removes trailing slash, keeps meaningful params (page, id, q, etc.).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    # Lowercase scheme and host
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = parsed.netloc.lower()

    # Remove trailing slash from path
    path = parsed.path.rstrip("/") or "/"

    # Filter query params
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=False)
        filtered = {k: v for k, v in params.items() if k.lower() not in STRIP_PARAMS}
        query = urlencode(filtered, doseq=True) if filtered else ""
    else:
        query = ""

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


def extract_domain(url: str) -> str:
    """Extract the base domain from a URL (lowercase, no scheme)."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def is_url(url: str) -> bool:
    """Check if a string looks like a URL."""
    try:
        result = urlparse(url)
        return bool(result.scheme) and bool(result.netloc)
    except Exception:
        return False
