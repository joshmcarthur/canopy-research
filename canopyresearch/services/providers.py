"""
Source provider abstraction for canopyresearch.

This module provides a pluggable provider system for fetching documents
from various content sources (RSS, Hacker News, Subreddit, etc.).
"""

from typing import Any

from canopyresearch.models import Source


class BaseSourceProvider:
    """
    Abstract base class for any content provider.

    Subclasses must implement fetch_documents() to return normalized
    document dictionaries.
    """

    def __init__(self, source: Source):
        """
        Initialize provider with a Source instance.

        Args:
            source: The Source model instance to fetch documents for
        """
        self.source = source

    def fetch_documents(self) -> list[dict[str, Any]]:
        """
        Fetch and return normalized documents from the source.

        Returns:
            List of normalized document dictionaries with keys:
            - title: str
            - url: str
            - content: str
            - published_at: datetime
            - metadata: dict (optional)

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement fetch_documents()")


class RSSProvider(BaseSourceProvider):
    """Provider for RSS feed sources."""

    def fetch_documents(self) -> list[dict[str, Any]]:
        """
        Fetch documents from an RSS feed.

        Returns:
            List of normalized document dictionaries
        """
        # Stub implementation for Phase 1
        # TODO: Implement RSS feed parsing
        return []


class HackerNewsProvider(BaseSourceProvider):
    """Provider for Hacker News sources."""

    def fetch_documents(self) -> list[dict[str, Any]]:
        """
        Fetch documents from Hacker News.

        Returns:
            List of normalized document dictionaries
        """
        # Stub implementation for Phase 1
        # TODO: Implement Hacker News API integration
        return []


class SubredditProvider(BaseSourceProvider):
    """Provider for Reddit subreddit sources."""

    def fetch_documents(self) -> list[dict[str, Any]]:
        """
        Fetch documents from a Reddit subreddit.

        Returns:
            List of normalized document dictionaries
        """
        # Stub implementation for Phase 1
        # TODO: Implement Reddit API integration
        return []


# Provider registry mapping provider_type strings to provider classes
PROVIDER_REGISTRY = {
    "rss": RSSProvider,
    "hackernews": HackerNewsProvider,
    "subreddit": SubredditProvider,
}


def get_provider_class(provider_type: str) -> type[BaseSourceProvider]:
    """
    Get the provider class for a given provider type.

    Args:
        provider_type: String identifier for the provider type (e.g., "rss", "hackernews")

    Returns:
        Provider class (subclass of BaseSourceProvider)

    Raises:
        ValueError: If provider_type is not registered
    """
    provider_class = PROVIDER_REGISTRY.get(provider_type)
    if provider_class is None:
        raise ValueError(f"Unknown provider type: {provider_type}")
    return provider_class
