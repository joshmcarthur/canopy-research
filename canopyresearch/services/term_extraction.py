"""
Term extraction service for source discovery.

Extracts meaningful search terms from text, documents, and workspace context.
Uses an OpenAI-compatible chat API for semantic extraction, with a simple
regex-based fallback when no API is configured.
"""

import json
import logging
import os
import re

from canopyresearch.models import Document

logger = logging.getLogger(__name__)

# Common stopwords to filter out
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "was",
    "are",
    "were",
    "been",
    "be",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "should",
    "could",
    "may",
    "might",
    "must",
    "can",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "they",
    "them",
    "their",
    "there",
    "then",
    "than",
    "what",
    "which",
    "who",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "every",
    "some",
    "any",
    "no",
    "not",
    "only",
    "just",
    "more",
    "most",
    "very",
    "too",
    "so",
    "such",
    "about",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "up",
    "down",
    "out",
    "off",
    "over",
    "under",
    "again",
    "further",
    "once",
}


def extract_terms_from_text(text: str, min_length: int = 3) -> list[str]:
    """
    Extract meaningful terms from text using simple tokenisation.

    Lowercases, removes punctuation, filters stopwords and short words,
    and returns unique terms in order of first appearance.
    """
    if not text or not text.strip():
        return []

    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()

    seen: set[str] = set()
    unique_terms: list[str] = []
    for word in words:
        if word not in STOPWORDS and len(word) >= min_length and word not in seen:
            seen.add(word)
            unique_terms.append(word)

    return unique_terms


def extract_terms_from_document(document: Document, use_llm: bool = True) -> list[str]:
    """
    Extract terms from a document's title and content.

    Attempts LLM extraction first (if configured), falls back to simple extraction.
    """
    if use_llm and (document.title or document.content):
        combined = "\n\n".join(filter(None, [document.title, document.content])).strip()
        try:
            llm_terms = extract_terms_with_llm(combined, context="document")
            if llm_terms:
                return llm_terms
        except Exception as e:
            logger.debug("LLM extraction failed for document %s, using simple: %s", document.id, e)

    # Simple fallback
    terms: list[str] = []
    seen: set[str] = set()
    for text in filter(None, [document.title, document.content]):
        for term in extract_terms_from_text(text):
            if term not in seen:
                seen.add(term)
                terms.append(term)
    return terms


def extract_terms_with_llm(
    text: str,
    context: str | None = None,
    model: str | None = None,
) -> list[str]:
    """
    Extract search terms using an OpenAI-compatible chat API.

    Configuration via environment variables:
        OPENAI_API_KEY   — API key (required; use any non-empty string for local servers)
        OPENAI_API_BASE  — Base URL (default: https://api.openai.com/v1)
        TERM_EXTRACTION_MODEL — Model name (default: gpt-4o-mini)

    Falls back to simple extraction if no API key is configured or the call fails.
    """
    if not text or not text.strip():
        return []

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.debug("OPENAI_API_KEY not set, using simple term extraction")
        return extract_terms_from_text(text)

    try:
        import openai
    except ImportError:
        logger.warning("openai package not installed, using simple term extraction")
        return extract_terms_from_text(text)

    api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    model_name = model or os.environ.get("TERM_EXTRACTION_MODEL", "gpt-4o-mini")

    context_str = f"Context: {context}\n\n" if context else ""
    prompt = (
        f"Extract 5-15 key search terms from the following text.\n"
        f"Focus on important concepts, technical terms, and domain-specific vocabulary.\n"
        f"Include synonyms where useful (e.g. 'ML' → 'machine learning').\n"
        f"Avoid generic words like 'research', 'article', 'document'.\n\n"
        f"{context_str}Text: {text}\n\n"
        f"Return ONLY a JSON array of strings, no markdown, no explanation. "
        f'Example: ["term1", "term2", "term3"]'
    )

    try:
        client = openai.OpenAI(api_key=api_key, base_url=api_base)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that extracts key search terms. Always return valid JSON arrays.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )

        content = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        terms = json.loads(content)
        if isinstance(terms, list):
            return [str(t).lower().strip() for t in terms if t and len(str(t).strip()) >= 2]
        return []

    except Exception as e:
        logger.warning("LLM term extraction failed, falling back to simple extraction: %s", e)
        return extract_terms_from_text(text)
