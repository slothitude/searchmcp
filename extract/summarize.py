"""Extractive summarization — no LLM, sentence scoring with non-Latin fallback."""

import logging
import re
import unicodedata
from collections import Counter

logger = logging.getLogger(__name__)

# Languages where sentence splitting works well
_SENTENCE_LANGS = {"en", "fr", "de", "es", "it", "pt", "nl", "ru", "ja", "zh", "ko"}

# Common English stopwords (small set, for keyword scoring)
_STOPWORDS = frozenset(
    "the a an is are was were be been being have has had do does did will "
    "would shall should may might can could of at in on to for with by "
    "from about as into through during before after above below between "
    "out off over under again further then once here there when where why "
    "how all both each few more most other some such no nor not only own "
    "same so than too very and but or if while this that these those it "
    "its what which who whom i me my we our you your he him his she her "
    "they them their what".split()
)


def summarize(text: str, max_sentences: int = 10, style: str = "bullets",
              title: str = "") -> str:
    """Extractive summarization: score sentences, return top N.

    Uses position, keyword relevance to title, length, and TF scoring.
    """
    if not text or not text.strip():
        return ""

    language = _detect_script(text)

    # Non-Latin fallback: paragraph-level extraction
    if language not in _SENTENCE_LANGS:
        return _paragraph_fallback(text, max_sentences, title)

    sentences = _split_sentences(text)
    if len(sentences) <= max_sentences:
        return _format_output(sentences, style)

    title_terms = set(_tokenize(title.lower())) if title else set()

    # Build TF from document
    doc_tokens = _tokenize(text.lower())
    tf = Counter(doc_tokens)

    scored = []
    for i, sent in enumerate(sentences):
        score = 0.0

        # Position score: first 3 sentences + last sentence
        if i < 3:
            score += 0.3 * (3 - i) / 3
        if i == len(sentences) - 1:
            score += 0.2

        # Title keyword relevance
        if title_terms:
            sent_terms = set(_tokenize(sent.lower()))
            overlap = sent_terms & title_terms
            if title_terms:
                score += 0.3 * (len(overlap) / len(title_terms))

        # Length score: prefer 20-200 char sentences
        sent_len = len(sent)
        if 20 <= sent_len <= 200:
            score += 0.1
        elif sent_len < 20:
            score -= 0.1

        # TF score: important terms
        sent_tokens = _tokenize(sent.lower())
        if sent_tokens:
            avg_tf = sum(tf.get(t, 0) for t in sent_tokens) / len(sent_tokens)
            # Normalize by document average
            doc_avg = sum(tf.values()) / max(1, len(tf))
            score += 0.1 * (avg_tf / max(0.001, doc_avg))

        scored.append((score, sent))

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [s for _, s in scored[:max_sentences]]

    # Re-sort by original position for readability
    top.sort(key=lambda s: sentences.index(s))

    return _format_output(top, style)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Remove markdown headings for sentence splitting
    clean = re.sub(r"^#{1,6}\s.*$", "", text, flags=re.MULTILINE)
    # Split on sentence-ending punctuation followed by space/newline
    sentences = re.split(r'(?<=[.!?])\s+', clean.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer with stopword filtering."""
    words = re.findall(r'\b[a-z]{2,}\b', text)
    return [w for w in words if w not in _STOPWORDS]


def _detect_script(text: str) -> str:
    """Detect if text is primarily Latin-based or another script."""
    latin_count = 0
    total_count = 0
    sample = text[:1000]
    for ch in sample:
        if ch.isalpha():
            total_count += 1
            if unicodedata.category(ch).startswith("L"):
                # Check if it's a Latin character
                cp = ord(ch)
                if (0x0041 <= cp <= 0x024F or  # Basic Latin + Latin Extended
                    0x1E00 <= cp <= 0x1EFF):    # Latin Extended Additional
                    latin_count += 1
    if total_count == 0:
        return "en"
    return "en" if latin_count / total_count > 0.7 else "other"


def _paragraph_fallback(text: str, max_count: int, title: str) -> str:
    """For non-Latin text: return first N paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) <= max_count:
        return "\n\n".join(paragraphs)

    # Score paragraphs by title keyword overlap and position
    title_terms = set(_tokenize(title.lower())) if title else set()
    scored = []
    for i, para in enumerate(paragraphs):
        score = 1.0 - (i / len(paragraphs))  # position bonus
        if title_terms:
            para_text = para.lower()
            overlap = sum(1 for t in title_terms if t in para_text)
            score += 0.5 * overlap
        scored.append((score, para))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [p for _, p in scored[:max_count]]
    return "\n\n".join(top)


def _format_output(items: list[str], style: str) -> str:
    """Format extracted sentences/paragraphs."""
    if style == "bullets":
        return "\n".join(f"- {item}" for item in items)
    return " ".join(items)
