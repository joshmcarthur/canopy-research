"""
Tests for canopyresearch source providers.
"""

from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase

from canopyresearch.models import Source, Workspace
from canopyresearch.services.ingestion import ingest_source
from canopyresearch.services.providers import (
    BaseSourceProvider,
    HackerNewsProvider,
    RSSProvider,
    SubredditProvider,
    _extract_links_from_html,
    _is_url_allowed,
    extract_article_content,
    get_provider_class,
)
from canopyresearch.tests.fixtures import ALGOLIA_RESPONSE, REDDIT_RESPONSE, RSS_MINIMAL

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
            config={"url": "https://example.com/feed.xml", "fetch_full_article": False},
        )

    @patch("canopyresearch.services.providers.requests.get")
    def test_rss_provider_fetch_returns_entries_from_valid_feed(self, mock_get):
        """Test RSSProvider.fetch returns list of raw dicts from valid feed."""
        mock_resp = MagicMock()
        mock_resp.content = RSS_MINIMAL
        mock_resp.headers = {"Content-Type": "application/xml"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = RSSProvider(self.source)
        result = provider.fetch()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIn("link", result[0])
        self.assertIn("title", result[0])
        self.assertEqual(result[0]["title"], "Item 1")
        self.assertEqual(result[0]["link"], "https://example.com/1")

    @patch("canopyresearch.services.providers.requests.get")
    def test_rss_provider_fetch_handles_404(self, mock_get):
        """Test RSSProvider.fetch handles 404."""
        mock_get.side_effect = requests.HTTPError("404")

        provider = RSSProvider(self.source)
        with self.assertRaises(requests.HTTPError):
            provider.fetch()

    @patch("canopyresearch.services.providers.requests.get")
    def test_rss_provider_fetch_handles_timeout(self, mock_get):
        """Test RSSProvider.fetch handles timeout."""
        mock_get.side_effect = requests.Timeout()

        provider = RSSProvider(self.source)
        with self.assertRaises(requests.Timeout):
            provider.fetch()

    def test_rss_provider_normalize_produces_required_schema(self):
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

    def test_rss_provider_normalize_handles_missing_published(self):
        """Test RSSProvider.normalize handles missing published."""
        provider = RSSProvider(self.source)
        raw = {"id": "x", "title": "T", "link": "https://x.com", "summary": "S"}
        out = provider.normalize(raw)
        self.assertIsNotNone(out["published_at"])

    @patch("canopyresearch.services.providers.requests.get")
    def test_rss_extract_body_links_emits_link_docs(self, mock_get):
        """Test extract_body_links emits one doc per link, not newsletter entry."""
        html_body = '<p>Check <a href="https://external.com/a">A</a> and <a href="https://external.com/b">B</a></p>'
        rss_with_links = (
            b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>Newsletter</title><link>https://newsletter.com</link>
<description>"""
            + html_body.encode()
            + b"""</description><guid>n1</guid></item>
</channel></rss>"""
        )
        mock_resp = MagicMock()
        mock_resp.content = rss_with_links
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        self.source.config = {
            "url": "https://example.com/feed.xml",
            "extract_body_links": True,
            "fetch_full_article": False,
        }
        self.source.save()

        provider = RSSProvider(self.source)
        result = provider.fetch()
        self.assertEqual(len(result), 2)  # 2 links, no newsletter entry
        urls = [r["link"] for r in result]
        self.assertIn("https://external.com/a", urls)
        self.assertIn("https://external.com/b", urls)

    def test_rss_extract_body_links_filters_mailto_and_hash(self):
        """Test extract_body_links filters mailto and hash links."""
        html = '<a href="mailto:foo@bar.com">Email</a> <a href="#anchor">Anchor</a> <a href="https://good.com">Good</a>'
        links = _extract_links_from_html(html)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][0], "https://good.com")

    @patch("canopyresearch.services.providers.requests.get")
    def test_rss_extract_body_links_respects_max_links_per_entry(self, mock_get):
        """Test extract_body_links respects max_links_per_entry."""
        links_html = " ".join(f'<a href="https://example.com/{i}">Link {i}</a>' for i in range(100))
        rss = (
            b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>F</title>
<item><title>N</title><link>https://n.com</link><description>"""
            + links_html.encode()
            + b"""</description><guid>g</guid></item>
</channel></rss>"""
        )
        mock_resp = MagicMock()
        mock_resp.content = rss
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        self.source.config = {
            "url": "https://example.com/feed.xml",
            "extract_body_links": True,
            "max_links_per_entry": 10,
            "fetch_full_article": False,
        }
        self.source.save()

        provider = RSSProvider(self.source)
        result = provider.fetch()
        self.assertLessEqual(len(result), 10)

    @patch("canopyresearch.services.providers.requests.get")
    def test_rss_fetch_full_article_extracts_content(self, mock_get):
        """Test fetch_full_article extracts content when enabled."""
        mock_resp_feed = MagicMock()
        mock_resp_feed.content = RSS_MINIMAL
        mock_resp_feed.headers = {"Content-Type": "application/xml"}
        mock_resp_feed.raise_for_status = MagicMock()

        html_content = "<html><body><article><p>Article body text</p></article></body></html>"
        html_bytes = html_content.encode("utf-8")
        mock_resp_article = MagicMock()
        mock_resp_article.content = html_bytes
        mock_resp_article.headers = {"Content-Type": "text/html"}
        mock_resp_article.raise_for_status = MagicMock()
        mock_resp_article.iter_content.return_value = [html_bytes]

        # Feed + 2 article URLs (example.com/1 and example.com/2)
        mock_get.side_effect = [mock_resp_feed, mock_resp_article, mock_resp_article]

        self.source.config = {"url": "https://example.com/feed.xml", "fetch_full_article": True}
        self.source.save()

        provider = RSSProvider(self.source)
        result = provider.fetch()
        self.assertGreater(len(result), 0)
        # First entry's link is https://example.com/1 - we mock that to return HTML
        self.assertIn("extracted_content", result[0])
        self.assertIn("Article body text", result[0]["extracted_content"])

    @patch("canopyresearch.services.providers.requests.get")
    def test_rss_fetch_returns_empty_when_no_url(self, mock_get):
        """Test fetch returns empty when config has no url."""
        self.source.config = {}
        self.source.save()
        provider = RSSProvider(self.source)
        result = provider.fetch()
        self.assertEqual(result, [])
        mock_get.assert_not_called()


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
            config={"fetch_full_article": False},
        )

    @patch("canopyresearch.services.providers.requests.get")
    def test_hackernews_provider_fetch_returns_stories_from_algolia(self, mock_get):
        """Test HackerNewsProvider.fetch returns raw docs from Algolia."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = ALGOLIA_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = HackerNewsProvider(self.source)
        result = provider.fetch()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "Test Story")
        self.assertEqual(result[0]["objectID"], "123")

    @patch("canopyresearch.services.providers.requests.get")
    def test_hackernews_provider_fetch_respects_listing_config(self, mock_get):
        """Test fetch respects listing config (search_by_date for new)."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"hits": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        self.source.config = {"listing": "new", "fetch_full_article": False}
        self.source.save()
        provider = HackerNewsProvider(self.source)
        provider.fetch()
        call_url = mock_get.call_args[0][0]
        self.assertIn("search_by_date", call_url)
        self.assertIn("tags=story", call_url)

    @patch("canopyresearch.services.providers.requests.get")
    def test_hackernews_provider_fetch_respects_limit(self, mock_get):
        """Test fetch respects limit config."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"hits": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        self.source.config = {"limit": 25, "fetch_full_article": False}
        self.source.save()
        provider = HackerNewsProvider(self.source)
        provider.fetch()
        call_url = mock_get.call_args[0][0]
        self.assertIn("hitsPerPage=25", call_url)

    def test_hackernews_provider_normalize_algolia_hit_produces_schema(self):
        """Test normalize produces schema from Algolia hit."""
        provider = HackerNewsProvider(self.source)
        raw = {
            "objectID": "123",
            "title": "Test",
            "url": "https://example.com",
            "author": "user",
            "points": 42,
            "created_at_i": 1700000000,
        }
        out = provider.normalize(raw)
        self.assertEqual(out["external_id"], "123")
        self.assertEqual(out["title"], "Test")
        self.assertEqual(out["url"], "https://example.com")
        self.assertEqual(out["metadata"]["by"], "user")
        self.assertEqual(out["metadata"]["score"], 42)

    def test_hackernews_provider_normalize_ask_hn_null_url(self):
        """Test normalize uses HN permalink when url is null (Ask HN)."""
        provider = HackerNewsProvider(self.source)
        raw = {
            "objectID": "456",
            "title": "Ask HN: Question?",
            "url": None,
            "author": "user",
            "points": 5,
            "created_at_i": 1700000000,
        }
        out = provider.normalize(raw)
        self.assertIn("news.ycombinator.com", out["url"])
        self.assertIn("id=456", out["url"])

    @patch("canopyresearch.services.providers.requests.get")
    def test_hackernews_provider_fetch_handles_api_error(self, mock_get):
        """Test fetch handles API error."""
        mock_get.side_effect = requests.HTTPError("500")

        provider = HackerNewsProvider(self.source)
        with self.assertRaises(requests.HTTPError):
            provider.fetch()


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
            config={"subreddit": "python", "fetch_full_article": False},
        )

    @patch("canopyresearch.services.providers.requests.get")
    def test_subreddit_provider_fetch_returns_posts_without_oauth(self, mock_get):
        """Test fetch returns posts from Reddit JSON endpoint."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = REDDIT_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = SubredditProvider(self.source)
        result = provider.fetch()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Test Post")
        self.assertEqual(result[0]["id"], "abc123")

    @patch("canopyresearch.services.providers.requests.get")
    def test_subreddit_provider_fetch_builds_correct_url(self, mock_get):
        """Test fetch builds correct URL for listing and timeframe."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"children": []}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        self.source.config = {
            "subreddit": "python",
            "listing": "top",
            "timeframe": "week",
            "fetch_full_article": False,
        }
        self.source.save()
        provider = SubredditProvider(self.source)
        provider.fetch()
        call_url = mock_get.call_args[0][0]
        self.assertIn("/r/python/top", call_url)
        self.assertIn("t=week", call_url)

    @patch("canopyresearch.services.providers.requests.get")
    def test_subreddit_provider_fetch_includes_user_agent(self, mock_get):
        """Test fetch includes User-Agent header."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"children": []}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = SubredditProvider(self.source)
        provider.fetch()
        call_kwargs = mock_get.call_args[1]
        self.assertIn("User-Agent", call_kwargs["headers"])

    def test_subreddit_provider_normalize_reddit_post_produces_schema(self):
        """Test normalize produces schema from Reddit post."""
        provider = SubredditProvider(self.source)
        raw = {
            "id": "abc",
            "title": "Title",
            "selftext": "Body",
            "url": "https://example.com",
            "permalink": "/r/python/comments/abc/",
            "author": "user",
            "subreddit": "python",
            "score": 10,
            "created_utc": 1700000000,
        }
        out = provider.normalize(raw)
        self.assertEqual(out["external_id"], "abc")
        self.assertEqual(out["title"], "Title")
        self.assertEqual(out["url"], "https://example.com")
        self.assertEqual(out["content"], "Body")
        self.assertEqual(out["metadata"]["author"], "user")

    def test_subreddit_provider_normalize_uses_permalink_for_self_post(self):
        """Test normalize uses permalink when url is reddit self post."""
        provider = SubredditProvider(self.source)
        raw = {
            "id": "abc",
            "title": "Self",
            "selftext": "Self body",
            "url": "https://reddit.com/r/python/comments/abc/",
            "permalink": "/r/python/comments/abc/self/",
            "author": "user",
            "subreddit": "python",
            "score": 5,
            "created_utc": 1700000000,
        }
        out = provider.normalize(raw)
        self.assertIn("reddit.com", out["url"])
        self.assertEqual(out["content"], "Self body")

    @patch("canopyresearch.services.providers.requests.get")
    @patch("canopyresearch.services.providers.requests.post")
    def test_subreddit_provider_fetch_oauth_when_config_present(self, mock_post, mock_get):
        """Test fetch uses OAuth when config has credentials."""
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "fake_token"}
        mock_token_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_token_resp

        mock_reddit_resp = MagicMock()
        mock_reddit_resp.json.return_value = REDDIT_RESPONSE
        mock_reddit_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_reddit_resp

        self.source.config = {
            "subreddit": "python",
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtok",
            "fetch_full_article": False,
        }
        self.source.save()

        provider = SubredditProvider(self.source)
        result = provider.fetch()
        self.assertEqual(len(result), 1)
        mock_post.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertIn("Bearer", call_kwargs["headers"]["Authorization"])
        self.assertIn("oauth.reddit.com", mock_get.call_args[0][0])

    @patch("canopyresearch.services.providers.requests.get")
    def test_subreddit_provider_fetch_returns_empty_when_no_subreddit(self, mock_get):
        """Test fetch returns empty when config has no subreddit."""
        self.source.config = {}
        self.source.save()
        provider = SubredditProvider(self.source)
        result = provider.fetch()
        self.assertEqual(result, [])
        mock_get.assert_not_called()


class IsUrlAllowedTest(TestCase):
    """Test _is_url_allowed URL validation."""

    def test_allows_valid_domain(self):
        """Test that valid domains are allowed."""
        self.assertTrue(_is_url_allowed("https://example.com/article"))
        self.assertTrue(_is_url_allowed("http://www.github.com"))
        self.assertTrue(_is_url_allowed("https://subdomain.example.org/path"))

    def test_blocks_ipv4_addresses(self):
        """Test that IPv4 addresses are blocked."""
        self.assertFalse(_is_url_allowed("http://192.168.1.1"))
        self.assertFalse(_is_url_allowed("https://8.8.8.8"))
        self.assertFalse(_is_url_allowed("http://127.0.0.1:8080"))

    def test_blocks_ipv6_addresses(self):
        """Test that IPv6 addresses are blocked."""
        self.assertFalse(_is_url_allowed("http://[::1]"))
        self.assertFalse(_is_url_allowed("https://[2001:db8::1]"))
        self.assertFalse(_is_url_allowed("http://[fe80::1]:8080"))

    def test_blocks_private_ip_ranges(self):
        """Test that private IP ranges are blocked."""
        self.assertFalse(_is_url_allowed("http://10.0.0.1"))
        self.assertFalse(_is_url_allowed("https://172.16.0.1"))
        self.assertFalse(_is_url_allowed("http://192.168.0.1"))

    def test_blocks_loopback_addresses(self):
        """Test that loopback addresses are blocked."""
        self.assertFalse(_is_url_allowed("http://127.0.0.1"))
        self.assertFalse(_is_url_allowed("https://localhost"))
        self.assertFalse(_is_url_allowed("http://[::1]"))

    def test_blocks_link_local_addresses(self):
        """Test that link-local addresses are blocked."""
        self.assertFalse(_is_url_allowed("http://169.254.0.1"))
        self.assertFalse(_is_url_allowed("http://[fe80::1]"))

    def test_blocks_ip_in_hostname(self):
        """Test that hostnames containing IP segments are blocked."""
        self.assertFalse(_is_url_allowed("http://127.0.0.1.example.com"))
        self.assertFalse(_is_url_allowed("https://192.168.1.1.malicious.com"))

    def test_blocks_invalid_urls(self):
        """Test that invalid URLs are blocked."""
        self.assertFalse(_is_url_allowed("not-a-url"))
        self.assertFalse(_is_url_allowed(""))
        self.assertFalse(_is_url_allowed("http://"))


class ExtractArticleContentTest(TestCase):
    """Test extract_article_content helper."""

    @patch("canopyresearch.services.providers.requests.get")
    def test_extract_article_content_returns_text(self, mock_get):
        """Test extract_article_content returns extracted text."""
        html = "<html><head></head><body><article><p>Main content here</p></article></body></html>"
        mock_resp = MagicMock()
        mock_resp.content = html.encode("utf-8")
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_content.return_value = [html.encode("utf-8")]
        mock_get.return_value = mock_resp

        result = extract_article_content("https://example.com/article")
        self.assertIsNotNone(result)
        self.assertIn("Main content here", result)
        self.assertNotIn("<p>", result)

    @patch("canopyresearch.services.providers.requests.get")
    def test_extract_article_content_returns_none_on_404(self, mock_get):
        """Test extract_article_content returns None on 404."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
        mock_get.return_value = mock_resp

        result = extract_article_content("https://example.com/missing")
        self.assertIsNone(result)

    @patch("canopyresearch.services.providers.requests.get")
    def test_extract_article_content_returns_none_on_timeout(self, mock_get):
        """Test extract_article_content returns None on timeout."""
        mock_get.side_effect = requests.Timeout()

        result = extract_article_content("https://example.com/slow")
        self.assertIsNone(result)

    def test_extract_article_content_blocks_ip_addresses(self):
        """Test extract_article_content blocks IP addresses."""
        result = extract_article_content("http://127.0.0.1")
        self.assertIsNone(result)
        result = extract_article_content("https://192.168.1.1")
        self.assertIsNone(result)
        result = extract_article_content("http://[::1]")
        self.assertIsNone(result)

    @patch("canopyresearch.services.providers.requests.get")
    def test_extract_article_content_enforces_size_limit(self, mock_get):
        """Test extract_article_content enforces max response size."""
        from canopyresearch.services.providers import MAX_RESPONSE_SIZE

        # Create a response that exceeds MAX_RESPONSE_SIZE
        large_chunk = b"x" * (MAX_RESPONSE_SIZE + 1)
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_content.return_value = [large_chunk]
        mock_get.return_value = mock_resp

        result = extract_article_content("https://example.com/large")
        self.assertIsNone(result)


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


class IngestSourceProviderIntegrationTest(TestCase):
    """Integration tests for ingest_source with providers."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.source = Source.objects.create(
            workspace=self.workspace,
            name="Test RSS",
            provider_type="rss",
            config={"url": "https://example.com/feed.xml", "fetch_full_article": False},
            status="healthy",
        )

    @patch("canopyresearch.services.providers.requests.get")
    def test_ingest_source_with_rss_provider_creates_documents(self, mock_get):
        """Test ingest_source creates documents from RSS provider."""
        mock_resp = MagicMock()
        mock_resp.content = RSS_MINIMAL
        mock_resp.headers = {"Content-Type": "application/xml"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        found, created = ingest_source(self.source)
        self.assertEqual(found, 2)
        self.assertGreaterEqual(created, 1)
        self.assertEqual(
            self.workspace.documents.count(),
            2,
        )

    @patch("canopyresearch.services.providers.requests.get")
    def test_ingest_source_propagates_provider_exception(self, mock_get):
        """Test ingest_source propagates provider exception and marks error."""
        mock_get.side_effect = requests.HTTPError("500")

        with self.assertRaises(requests.HTTPError):
            ingest_source(self.source)
        self.source.refresh_from_db()
        self.assertEqual(self.source.status, "error")
        self.assertGreater(self.source.consecutive_failures, 0)
