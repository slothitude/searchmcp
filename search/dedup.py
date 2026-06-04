"""URL and title deduplication for search results."""

from difflib import SequenceMatcher

from utils.urls import normalize_url


def deduplicate(results: list[dict], similarity_threshold: float = 0.85) -> list[dict]:
    """Remove duplicate search results by URL normalization and title similarity.

    Keeps the first (highest scored) result.
    """
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    deduped = []

    for result in results:
        url = normalize_url(result.get("url", ""))
        title = result.get("title", "")

        # URL dedup
        if url in seen_urls:
            continue

        # Title similarity dedup
        is_dup = False
        for existing_title in seen_titles:
            ratio = SequenceMatcher(None, title.lower(), existing_title.lower()).ratio()
            if ratio > similarity_threshold:
                is_dup = True
                break

        if is_dup:
            continue

        seen_urls.add(url)
        seen_titles.append(title)
        deduped.append(result)

    return deduped
