"""Tier 1 extraction — trafilatura with broad recall → precision retry."""

import logging
import trafilatura

logger = logging.getLogger(__name__)


def extract_broad(html: str, url: str) -> dict:
    """Extract content with favor_recall=True (broad, catches more text)."""
    try:
        result = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_metadata=True,
            include_tables=True,
            deduplicate=True,
            include_links=False,
            include_comments=False,
            include_images=False,
            favor_recall=True,
        )
        return {"text": result or "", "success": bool(result)}
    except Exception as e:
        logger.debug(f"Trafilatura broad extraction failed for {url[:60]}: {e}")
        return {"text": "", "success": False, "error": str(e)}


def extract_precision(html: str, url: str) -> dict:
    """Extract content with favor_precision=True (focused, cleaner output)."""
    try:
        result = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_metadata=True,
            include_tables=True,
            deduplicate=True,
            include_links=False,
            include_comments=False,
            include_images=False,
            favor_precision=True,
        )
        return {"text": result or "", "success": bool(result)}
    except Exception as e:
        logger.debug(f"Trafilatura precision extraction failed for {url[:60]}: {e}")
        return {"text": "", "success": False, "error": str(e)}


def extract_metadata(html: str, url: str) -> dict:
    """Extract just the metadata (title, author, date) without full body.

    Uses trafilatura's bare_extraction to get metadata quickly.
    """
    try:
        result = trafilatura.bare_extraction(
            html,
            url=url,
            include_comments=False,
            include_images=False,
            favor_recall=False,
        )
        if not result:
            return {}
        return {
            "title": result.get("title", ""),
            "author": result.get("author", ""),
            "date": result.get("date", ""),
            "description": result.get("description", ""),
            "sitename": result.get("sitename", ""),
        }
    except Exception as e:
        logger.debug(f"Metadata extraction failed: {e}")
        return {}
