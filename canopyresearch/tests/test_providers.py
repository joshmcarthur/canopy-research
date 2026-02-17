"""
Tests for canopyresearch source providers.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from canopyresearch.models import Source, Workspace
from canopyresearch.services.providers import (
    BaseSourceProvider,
    HackerNewsProvider,
    RSSProvider,
    SubredditProvider,
    get_provider_class,
)

User = get_user_model()


class BaseSourceProviderTest(TestCase):
    """Test BaseSourceProvider abstract class."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
            config={"url": "https://example.com/feed.xml"},
        )

    def test_base_provider_fetch_not_implemented(self):
        """Test that BaseSourceProvider.fetch raises NotImplementedError."""
        provider = BaseSourceProvider(self.source)
        with self.assertRaises(NotImplementedError):
            provider.fetch()

    def test_base_provider_normalize_not_implemented(self):
        """Test that BaseSourceProvider.normalize raises NotImplementedError."""
        provider = BaseSourceProvider(self.source)
        with self.assertRaises(NotImplementedError):
            provider.normalize({})

    def test_provider_initialization(self):
        """Test provider initialization with source."""
        provider = BaseSourceProvider(self.source)
        self.assertEqual(provider.source, self.source)


class RSSProviderTest(TestCase):
    """Test RSSProvider."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.source = Source.objects.create(
            workspace=self.workspace,
            name="Test RSS Source",
            provider_type="rss",
            config={"url": "https://example.com/feed.xml"},
        )

    def test_rss_provider_creation(self):
        """Test creating RSSProvider."""
        provider = RSSProvider(self.source)
        self.assertIsInstance(provider, BaseSourceProvider)
        self.assertEqual(provider.source, self.source)

    def test_rss_provider_fetch_returns_list(self):
        """Test RSSProvider.fetch returns list."""
        provider = RSSProvider(self.source)
        result = provider.fetch()
        self.assertIsInstance(result, list)

    def test_rss_provider_normalize_produces_schema(self):
        """Test RSSProvider.normalize produces required fields."""
        provider = RSSProvider(self.source)
        raw = {
            "id": "abc123",
            "title": "Test",
            "link": "https://example.com",
            "summary": "Content",
        }
        out = provider.normalize(raw)
        self.assertIn("external_id", out)
        self.assertIn("title", out)
        self.assertIn("url", out)
        self.assertIn("content", out)
        self.assertIn("published_at", out)
        self.assertIn("metadata", out)
        self.assertEqual(out["title"], "Test")
        self.assertEqual(out["url"], "https://example.com")


class HackerNewsProviderTest(TestCase):
    """Test HackerNewsProvider."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.source = Source.objects.create(
            workspace=self.workspace,
            name="Test HN Source",
            provider_type="hackernews",
            config={},
        )

    def test_hackernews_provider_creation(self):
        """Test creating HackerNewsProvider."""
        provider = HackerNewsProvider(self.source)
        self.assertIsInstance(provider, BaseSourceProvider)

    def test_hackernews_provider_fetch_returns_list(self):
        """Test HackerNewsProvider.fetch returns list."""
        provider = HackerNewsProvider(self.source)
        result = provider.fetch()
        self.assertIsInstance(result, list)

    def test_hackernews_provider_normalize_produces_schema(self):
        """Test HackerNewsProvider.normalize produces required fields."""
        provider = HackerNewsProvider(self.source)
        raw = {"id": 12345, "title": "HN Post", "url": "https://example.com", "by": "user"}
        out = provider.normalize(raw)
        self.assertEqual(out["external_id"], "12345")
        self.assertEqual(out["title"], "HN Post")


class SubredditProviderTest(TestCase):
    """Test SubredditProvider."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.source = Source.objects.create(
            workspace=self.workspace,
            name="Test Reddit Source",
            provider_type="subreddit",
            config={"subreddit": "python"},
        )

    def test_subreddit_provider_creation(self):
        """Test creating SubredditProvider."""
        provider = SubredditProvider(self.source)
        self.assertIsInstance(provider, BaseSourceProvider)

    def test_subreddit_provider_fetch_returns_list(self):
        """Test SubredditProvider.fetch returns list."""
        provider = SubredditProvider(self.source)
        result = provider.fetch()
        self.assertIsInstance(result, list)


class ProviderRegistryTest(TestCase):
    """Test provider registry and resolver."""

    def test_get_provider_class_rss(self):
        """Test getting RSS provider class."""
        provider_class = get_provider_class("rss")
        self.assertEqual(provider_class, RSSProvider)

    def test_get_provider_class_hackernews(self):
        """Test getting HackerNews provider class."""
        provider_class = get_provider_class("hackernews")
        self.assertEqual(provider_class, HackerNewsProvider)

    def test_get_provider_class_subreddit(self):
        """Test getting Subreddit provider class."""
        provider_class = get_provider_class("subreddit")
        self.assertEqual(provider_class, SubredditProvider)

    def test_get_provider_class_invalid(self):
        """Test getting invalid provider class raises ValueError."""
        with self.assertRaises(ValueError):
            get_provider_class("invalid_provider")
