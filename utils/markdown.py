"""Markdown helpers — truncation at sentence boundary, metadata blocks, cleanup."""

import re
import time
from html import unescape


def truncate_at_sentence(text: str, max_length: int) -> str:
    """Truncate text at a sentence boundary, keeping first 80% + last 20% of sentences."""
    if len(text) <= max_length:
        return text

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) <= 1:
        return text[:max_length].rsplit(" ", 1)[0] + "..."

    # Keep first 80% + last 20% of sentences
    n = len(sentences)
    keep_first = max(1, int(n * 0.8))
    result = " ".join(sentences[:keep_first])

    if len(result) > max_length:
        # Fall back to mid-sentence cut
        result = result[:max_length]
        last_space = result.rfind(" ")
        if last_space > max_length * 0.7:
            result = result[:last_space]
        result = result.rstrip() + "..."

    remaining = len(text) - len(result)
    result += f"\n\n<!-- truncated: {remaining} chars remaining -->"
    return result


def make_metadata_block(title: str = "", author: str = "", date: str = "",
                        site: str = "", url: str = "", word_count: int = 0,
                        language: str = "", extra: dict | None = None) -> str:
    """Build an HTML comment metadata block for the top of extracted content."""
    lines = ["<!-- meta"]
    if title:
        lines.append(f'title: "{_escape_attr(title)}"')
    if author:
        lines.append(f'author: "{_escape_attr(author)}"')
    if date:
        lines.append(f'date: "{date}"')
    if site:
        lines.append(f'site: "{site}"')
    if url:
        lines.append(f'url: "{url}"')
    if word_count:
        lines.append(f"words: {word_count}")
        lines.append(f'reading_time: "{max(1, word_count // 250)} min"')
    if language:
        lines.append(f'language: "{language}"')
    lines.append(f'fetched: "{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}"')
    if extra:
        for k, v in extra.items():
            lines.append(f'{k}: "{v}"')
    lines.append("-->")
    return "\n".join(lines)


def make_error_block(error_type: str, url: str, http_status: int | None = None,
                     message: str = "") -> str:
    """Build an error metadata block."""
    lines = ["<!-- meta"]
    lines.append(f"status: error")
    lines.append(f"error_type: {error_type}")
    if http_status is not None:
        lines.append(f"http_status: {http_status}")
    lines.append(f'url: "{_escape_attr(url)}"')
    if message:
        lines.append(f"message: \"{_escape_attr(message)}\"")
    lines.append("-->")
    return "\n".join(lines)


def strip_empty_headings(text: str) -> str:
    """Remove markdown headings with no following content."""
    lines = text.split("\n")
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if this is a heading
        if re.match(r"^#{1,6}\s", line):
            # Check if next non-empty line is content
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            # If next non-empty line is another heading or end of text, skip this heading
            if j >= len(lines) or re.match(r"^#{1,6}\s", lines[j]):
                i = j
                continue
        cleaned.append(line)
        i += 1
    return "\n".join(cleaned)


def cleanup_markdown(text: str) -> str:
    """General markdown cleanup: fix spacing, normalize headings, remove artifacts."""
    # Decode HTML entities
    text = unescape(text)
    # Remove excessive blank lines (keep max 2)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove trailing whitespace on lines
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Strip leading/trailing whitespace
    text = text.strip()
    return text


def _escape_attr(s: str) -> str:
    """Escape a string for use inside a quoted HTML attribute."""
    return s.replace('"', "&quot;").replace("\n", " ")
