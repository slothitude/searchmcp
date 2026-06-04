"""Post-processing pipeline — cleanup, metadata injection, smart truncation."""

import logging

from extract.tier1 import extract_metadata
from utils.urls import extract_domain
from utils.markdown import (make_metadata_block, make_error_block,
                            truncate_at_sentence, strip_empty_headings, cleanup_markdown)

logger = logging.getLogger(__name__)


def postprocess(text: str, url: str, html: str, max_length: int,
                include_metadata: bool) -> str:
    """Full post-processing pipeline for extracted content."""
    if not text or not text.strip():
        return make_error_block("extraction_error", url,
                                message="No content could be extracted")

    # Extract metadata from HTML (separate call to get clean metadata)
    meta = extract_metadata(html, url)

    # Cleanup
    text = cleanup_markdown(text)
    text = strip_empty_headings(text)

    # Truncate if needed
    if max_length and len(text) > max_length:
        text = truncate_at_sentence(text, max_length)

    # Build output
    parts = []

    if include_metadata:
        domain = extract_domain(url)
        word_count = len(text.split())
        meta_block = make_metadata_block(
            title=meta.get("title", ""),
            author=meta.get("author", ""),
            date=str(meta.get("date", "")),
            site=domain or "",
            url=url,
            word_count=word_count,
        )
        parts.append(meta_block)
        parts.append("")

    parts.append(text)

    return "\n".join(parts)
