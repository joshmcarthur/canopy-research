"""
Content extraction and cleaning service for canopyresearch.

Centralizes HTML-to-text extraction, text normalization, and content cleaning.
"""

import logging
import re

import requests
from lxml import html as lxml_html
from readability import Document as ReadabilityDocument

from canopyresearch.services.providers import (
    HTTP_TIMEOUT,
    MAX_RESPONSE_SIZE,
    USER_AGENT,
    _is_url_allowed,
)

logger = logging.getLogger(__name__)

# Maximum length for cleaned text (to prevent embedding issues with extremely long documents)
MAX_CLEANED_TEXT_LENGTH = 10000


def extract_html_to_text(html: str) -> str | None:
    """
    Extract clean text from HTML using readability and lxml.

    Returns plain text or None on failure.
    """
    if not html or not html.strip():
        return None

    try:
        doc = ReadabilityDocument(html)
        summary_html = doc.summary()
        if not summary_html or not summary_html.strip():
            return None
        tree = lxml_html.fromstring(summary_html)
        text = tree.text_content() if tree is not None else ""
        return text.strip() if text else None
    except (ValueError, TypeError, AttributeError) as e:
        logger.debug("Failed to extract text from HTML: %s", e)
        return None


def normalize_text(text: str) -> str:
    """
    Normalize text by cleaning whitespace and removing boilerplate remnants.

    - Normalizes whitespace (multiple spaces/newlines to single)
    - Removes excessive line breaks (more than 2 consecutive become 2)
    - Strips leading/trailing whitespace
    """
    if not text:
        return ""

    # First, normalize excessive line breaks (more than 2 consecutive become 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Then normalize other whitespace: multiple spaces/tabs to single space
    # But preserve newlines - replace spaces/tabs with space, but keep newlines
    text = re.sub(r"[ \t]+", " ", text)  # Multiple spaces/tabs to single space
    text = re.sub(r" *\n *", "\n", text)  # Remove spaces around newlines

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def clean_text(text: str, max_length: int | None = None) -> str:
    """
    Clean and normalize text content.

    Args:
        text: Raw text to clean
        max_length: Optional maximum length (truncates if exceeded)

    Returns:
        Cleaned text
    """
    cleaned = normalize_text(text)

    if max_length and len(cleaned) > max_length:
        # Truncate at word boundary if possible
        truncated = cleaned[:max_length].rsplit(" ", 1)[0]
        cleaned = truncated + "..." if truncated != cleaned[:max_length] else cleaned[:max_length]

    return cleaned


def extract_content_from_url(url: str) -> str | None:
    """
    Fetch URL and extract main article content.

    Validates URL against DENY patterns and enforces max response size.
    Returns cleaned text or None on failure.

    This is a re-extraction function for cases where providers only stored snippets.
    """
    # Validate URL against DENY patterns
    if not _is_url_allowed(url):
        logger.debug("URL not allowed: %s", url)
        return None

    try:
        # Stream response with max bytes cap
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, stream=True
        )
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            logger.debug("Non-HTML content type: %s", content_type)
            return None

        # Stream response content with size limit
        content_chunks = []
        total_size = 0

        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                total_size += len(chunk)
                if total_size > MAX_RESPONSE_SIZE:
                    logger.debug("Response exceeds max size: %s", url)
                    return None
                content_chunks.append(chunk)

        # Combine chunks
        html_bytes = b"".join(content_chunks)

        try:
            html = html_bytes.decode("utf-8", errors="replace")
        except (UnicodeDecodeError, AttributeError):
            logger.debug("Failed to decode HTML: %s", url)
            return None

        # Extract text from HTML
        raw_text = extract_html_to_text(html)
        if not raw_text:
            return None

        # Clean and normalize
        cleaned = clean_text(raw_text, max_length=MAX_CLEANED_TEXT_LENGTH)
        return cleaned if cleaned else None

    except (requests.RequestException, ValueError, TypeError) as e:
        logger.debug("Failed to extract content from URL %s: %s", url, e)
        return None


def extract_and_clean_content(content: str, url: str | None = None) -> str:
    """
    Extract and clean content, optionally re-fetching from URL if content is too short.

    Args:
        content: Existing content (may be a snippet)
        url: Optional URL to re-fetch if content seems incomplete

    Returns:
        Cleaned text content
    """
    # Clean existing content
    cleaned = clean_text(content, max_length=MAX_CLEANED_TEXT_LENGTH)

    # If content is very short and we have a URL, try re-extracting
    if url and len(cleaned) < 200:
        logger.debug(
            "Content seems incomplete (%d chars), re-extracting from URL: %s", len(cleaned), url
        )
        re_extracted = extract_content_from_url(url)
        if re_extracted and len(re_extracted) > len(cleaned):
            cleaned = re_extracted

    return cleaned
