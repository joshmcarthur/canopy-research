"""
Source provider abstraction for canopyresearch.

Providers fetch raw documents and normalize them to the internal schema.
The pipeline owns validation, hashing, deduplication, and persistence.
"""

from datetime import datetime
from typing import Any

from django.utils import timezone

from canopyresearch.models import Source

# Internal normalized document schema (all providers must output this)
NORMALIZED_SCHEMA_KEYS = {"external_id", "title", "url", "content", "published_at", "metadata"}


class BaseSourceProvider:
    """
    Abstract base class for any content provider.

    Providers fetch raw documents and normalize them.
    Subclasses must implement fetch() and normalize().
    """

    provider_type: str = "base"

    def __init__(self, source: Source):
        self.source = source

    def fetch(self) -> list[dict[str, Any]]:
        """
        Fetch and return raw provider documents.

        Returns provider-specific structure. Each raw doc will be passed to normalize().
        """
        raise NotImplementedError("Subclasses must implement fetch()")

    def normalize(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """
        Convert raw provider document to normalized schema.

        Must return dict with keys: external_id, title, url, content, published_at, metadata.
        """
        raise NotImplementedError("Subclasses must implement normalize()")


class RSSProvider(BaseSourceProvider):
    """Provider for RSS feed sources."""

    provider_type = "rss"

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw documents from an RSS feed."""
        # Stub implementation - TODO: Implement RSS feed parsing
        return []

    def normalize(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """Convert RSS entry to normalized schema."""
        published = raw_doc.get("published_parsed") or raw_doc.get("published")
        if isinstance(published, datetime):
            published_at = (
                timezone.make_aware(published) if timezone.is_naive(published) else published
            )
        else:
            published_at = timezone.now()
        return {
            "external_id": raw_doc.get("id") or raw_doc.get("guid"),
            "title": raw_doc.get("title", ""),
            "url": raw_doc.get("link", ""),
            "content": raw_doc.get("summary", "") or raw_doc.get("description", ""),
            "published_at": published_at,
            "metadata": {"author": raw_doc.get("author"), "tags": raw_doc.get("tags", [])},
        }


class HackerNewsProvider(BaseSourceProvider):
    """Provider for Hacker News sources."""

    provider_type = "hackernews"

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw documents from Hacker News."""
        # Stub implementation - TODO: Implement Hacker News API integration
        return []

    def normalize(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """Convert HN item to normalized schema."""
        from datetime import datetime as dt

        time_val = raw_doc.get("time")
        if time_val:
            published_at = timezone.make_aware(
                dt.fromtimestamp(time_val), timezone.get_default_timezone()
            )
        else:
            published_at = timezone.now()
        return {
            "external_id": str(raw_doc.get("id", "")),
            "title": raw_doc.get("title", ""),
            "url": raw_doc.get(
                "url", f"https://news.ycombinator.com/item?id={raw_doc.get('id', '')}"
            ),
            "content": raw_doc.get("text", "") or raw_doc.get("title", ""),
            "published_at": published_at,
            "metadata": {
                "by": raw_doc.get("by"),
                "score": raw_doc.get("score"),
                "type": raw_doc.get("type"),
            },
        }


class SubredditProvider(BaseSourceProvider):
    """Provider for Reddit subreddit sources."""

    provider_type = "subreddit"

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw documents from a Reddit subreddit."""
        # Stub implementation - TODO: Implement Reddit API integration
        return []

    def normalize(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        """Convert Reddit post to normalized schema."""
        from datetime import datetime as dt

        created = raw_doc.get("created_utc")
        if created:
            published_at = timezone.make_aware(
                dt.fromtimestamp(created), timezone.get_default_timezone()
            )
        else:
            published_at = timezone.now()
        return {
            "external_id": raw_doc.get("id", ""),
            "title": raw_doc.get("title", ""),
            "url": (
                raw_doc.get("url")
                or (
                    f"https://reddit.com{raw_doc.get('permalink', '')}"
                    if raw_doc.get("permalink")
                    else ""
                )
                or ""
            ),
            "content": raw_doc.get("selftext", "") or raw_doc.get("title", ""),
            "published_at": published_at,
            "metadata": {
                "author": raw_doc.get("author"),
                "subreddit": raw_doc.get("subreddit"),
                "score": raw_doc.get("score"),
            },
        }


PROVIDER_REGISTRY = {
    "rss": RSSProvider,
    "hackernews": HackerNewsProvider,
    "subreddit": SubredditProvider,
}


def get_provider_class(provider_type: str) -> type[BaseSourceProvider]:
    """
    Get the provider class for a given provider type.

    Raises:
        ValueError: If provider_type is not registered
    """
    provider_class = PROVIDER_REGISTRY.get(provider_type)
    if provider_class is None:
        raise ValueError(f"Unknown provider type: {provider_type}")
    return provider_class
