"""Tier 3 extraction — crawl4ai browser fallback + BeautifulSoup last resort."""

import logging
import re

logger = logging.getLogger(__name__)

_crawl4ai_available = None


def _check_crawl4ai() -> bool:
    """Check if crawl4ai is importable."""
    global _crawl4ai_available
    if _crawl4ai_available is None:
        try:
            import crawl4ai
            _crawl4ai_available = True
        except ImportError:
            _crawl4ai_available = False
    return _crawl4ai_available


async def extract_browser(url: str, cdp_url: str | None) -> dict:
    """Use crawl4ai to render a JS-heavy page via remote Chrome CDP.

    Returns {"text": markdown, "success": bool} or {"text": "", "success": False}
    if CDP is unavailable or fails.
    """
    if not cdp_url or not _check_crawl4ai():
        return {"text": "", "success": False, "error": "CDP not configured or crawl4ai not installed"}

    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

        browser_config = BrowserConfig(
            cdp_url=cdp_url,
            headless=True,
        )
        run_config = CrawlerRunConfig(
            wait_until="domcontentloaded",
            page_timeout=30000,
            remove_consent_popups=True,
            exclude_external_images=True,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)

        if not result or not result.markdown:
            return {"text": "", "success": False, "error": "No content from browser"}

        text = _clean_browser_output(result.markdown)
        return {"text": text, "success": bool(text)}
    except Exception as e:
        logger.warning(f"crawl4ai failed for {url[:60]}: {e}")
        return {"text": "", "success": False, "error": str(e)}


def extract_beautifulsoup(html: str, url: str = "") -> dict:
    """Last-resort BeautifulSoup extraction — plain text from stripped HTML."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                         "iframe", "noscript", "form"]):
            tag.decompose()

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        main = (soup.find("main") or soup.find("article") or
                soup.find("div", class_=re.compile(r"content|article|post|entry", re.I)) or
                soup.body)

        if not main:
            return {"text": "", "success": False}

        text = main.get_text(separator="\n", strip=True)
        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if title:
            text = f"# {title}\n\n{text}"

        return {"text": text, "success": bool(text)}
    except Exception as e:
        logger.debug(f"BeautifulSoup fallback failed: {e}")
        return {"text": "", "success": False, "error": str(e)}


def _clean_browser_output(markdown: str) -> str:
    """Clean up crawl4ai output — remove cookie consent text, normalize."""
    # Common cookie consent patterns
    patterns = [
        r"by continuing.*?agree",
        r"we use cookies.*?\.",
        r"this website uses cookies",
        r"cookie preferences",
        r"accept all cookies",
        r"manage cookie settings",
        r"cookie consent",
    ]
    lines = markdown.split("\n")
    cleaned = []
    for line in lines:
        skip = False
        line_lower = line.lower().strip()
        for pattern in patterns:
            if re.search(pattern, line_lower):
                skip = True
                break
        if not skip:
            cleaned.append(line)

    return "\n".join(cleaned).strip()
