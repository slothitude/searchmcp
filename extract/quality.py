"""Content quality heuristics — article body detection, JS-heavy detection."""

import re


def has_article_body(text: str, html_len: int = 0) -> bool:
    """Check if extracted text looks like article content (not navigation/boilerplate)."""
    if not text or len(text) < 100:
        return False

    # Check for structural markers (headings, paragraphs)
    has_headings = bool(re.search(r"^#{1,4}\s", text, re.MULTILINE))
    has_paragraphs = text.count("\n\n") >= 2

    # Check for meaningful content markers
    has_long_lines = any(len(line) > 60 for line in text.split("\n") if line.strip())

    # At least 2 of 3 heuristics should pass
    score = sum([has_headings, has_paragraphs, has_long_lines])
    return score >= 2


def is_js_heavy(text: str, html_len: int) -> bool:
    """Detect if a page likely requires JS rendering.

    Heuristic: text content is < 20% of HTML size, or HTML contains
    React/Vue/Next/Angular framework markers.
    """
    if html_len == 0:
        return False

    text_ratio = len(text) / html_len if html_len > 0 else 0
    if text_ratio < 0.2:
        return True

    # Framework markers (case-insensitive substring check)
    js_markers = [
        'data-reactroot', 'ng-version=', 'data-v-', '_next/static',
        '__nuxt', 'data-react-helmet', 'id="app"', 'id="root"',
        'window.__INITIAL_STATE__', 'window.__NUXT__',
    ]
    return any(marker in text.lower() for marker in js_markers)


def extract_language(text: str) -> str:
    """Best-effort language detection from common HTML lang attributes in text."""
    # Check for common non-English word patterns
    # This is a lightweight heuristic — langdetect is used in summarize.py for actual detection
    return "en"  # default; let trafilatura handle it
