"""
Tests for canopyresearch ingestion service.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from canopyresearch.models import Document, DocumentSource, Source, Workspace
from canopyresearch.services.ingestion import (
    compute_hash,
    ingest_source,
    mark_source_error,
    persist_document,
)

User = get_user_model()


class ComputeHashTest(TestCase):
    """Test compute_hash function."""

    def test_deterministic(self):
        """Same input produces same hash."""
        data = {"title": "Test", "url": "https://example.com", "content": "Body"}
        h1 = compute_hash(data)
        h2 = compute_hash(data)
        self.assertEqual(h1, h2)

    def test_different_content_different_hash(self):
        """Different content produces different hash."""
        data1 = {"title": "Test", "url": "https://example.com", "content": "Body A"}
        data2 = {"title": "Test", "url": "https://example.com", "content": "Body B"}
        self.assertNotEqual(compute_hash(data1), compute_hash(data2))

    def test_title_normalized(self):
        """Title is stripped and lowercased."""
        data1 = {"title": "  Test  ", "url": "u", "content": ""}
        data2 = {"title": "test", "url": "u", "content": ""}
        self.assertEqual(compute_hash(data1), compute_hash(data2))

    def test_content_truncated(self):
        """Content beyond 500 chars does not affect hash."""
        data1 = {"title": "T", "url": "u", "content": "x" * 600}
        data2 = {"title": "T", "url": "u", "content": "x" * 500 + "y" * 100}
        self.assertEqual(compute_hash(data1), compute_hash(data2))

    def test_handles_missing_fields(self):
        """Handles missing title, url, content."""
        data = {}
        h = compute_hash(data)
        self.assertEqual(len(h), 64)  # SHA-256 hex


class PersistDocumentTest(TestCase):
    """Test persist_document function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )

    def test_creates_document(self):
        """Persist creates new document."""
        data = {
            "external_id": "ext1",
            "title": "Title",
            "url": "https://example.com",
            "content": "Content",
            "published_at": timezone.now(),
            "metadata": {},
        }
        created = persist_document(self.workspace, self.source, data)
        self.assertTrue(created)
        doc = Document.objects.get(workspace=self.workspace, url=data["url"])
        self.assertEqual(doc.title, "Title")
        self.assertEqual(doc.external_id, "ext1")
        self.assertIsNotNone(doc.content_hash)
        self.assertIsNotNone(doc.ingested_at)
        self.assertTrue(DocumentSource.objects.filter(document=doc, source=self.source).exists())

    def test_deduplication_same_article_twice(self):
        """Same article twice returns False on second persist."""
        data = {
            "title": "Same",
            "url": "https://example.com/same",
            "content": "Same content",
            "published_at": timezone.now(),
            "metadata": {},
        }
        self.assertTrue(persist_document(self.workspace, self.source, data))
        self.assertFalse(persist_document(self.workspace, self.source, data))
        self.assertEqual(Document.objects.filter(workspace=self.workspace).count(), 1)

    def test_deduplication_same_article_two_sources(self):
        """Same article from two sources shares one document."""
        source2 = Source.objects.create(
            workspace=self.workspace,
            name="Source 2",
            provider_type="rss",
        )
        data = {
            "title": "Shared",
            "url": "https://example.com/shared",
            "content": "Shared content",
            "published_at": timezone.now(),
            "metadata": {},
        }
        persist_document(self.workspace, self.source, data)
        persist_document(self.workspace, source2, data)
        self.assertEqual(Document.objects.filter(workspace=self.workspace).count(), 1)
        doc = Document.objects.get(workspace=self.workspace)
        self.assertEqual(doc.sources.count(), 2)

    def test_rejects_empty_url(self):
        """Persist raises ValueError for empty URL."""
        data = {
            "title": "Title",
            "url": "",
            "content": "Content",
            "published_at": timezone.now(),
        }
        with self.assertRaises(ValueError) as cm:
            persist_document(self.workspace, self.source, data)
        self.assertIn("missing required URL", str(cm.exception))
        self.assertEqual(Document.objects.filter(workspace=self.workspace).count(), 0)

    def test_rejects_missing_url(self):
        """Persist raises ValueError for missing URL."""
        data = {
            "title": "Title",
            "content": "Content",
            "published_at": timezone.now(),
        }
        with self.assertRaises(ValueError) as cm:
            persist_document(self.workspace, self.source, data)
        self.assertIn("missing required URL", str(cm.exception))
        self.assertEqual(Document.objects.filter(workspace=self.workspace).count(), 0)

    def test_rejects_whitespace_only_url(self):
        """Persist raises ValueError for whitespace-only URL."""
        data = {
            "title": "Title",
            "url": "   ",
            "content": "Content",
            "published_at": timezone.now(),
        }
        with self.assertRaises(ValueError) as cm:
            persist_document(self.workspace, self.source, data)
        self.assertIn("missing required URL", str(cm.exception))
        self.assertEqual(Document.objects.filter(workspace=self.workspace).count(), 0)

    def test_validation_error_includes_external_id(self):
        """Validation error message includes external_id when available."""
        data = {
            "external_id": "ext123",
            "title": "Title",
            "url": "",
            "content": "Content",
        }
        with self.assertRaises(ValueError) as cm:
            persist_document(self.workspace, self.source, data)
        error_msg = str(cm.exception)
        self.assertIn("external_id='ext123'", error_msg)
        self.assertIn("source='Test Source'", error_msg)


class MarkSourceErrorTest(TestCase):
    """Test mark_source_error function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.source = Source.objects.create(
            workspace=self.workspace,
            name="Test",
            provider_type="rss",
            status="healthy",
            consecutive_failures=0,
            auto_pause_threshold=5,
        )

    def test_increments_failures(self):
        """Consecutive failures increments."""
        mark_source_error(self.source, Exception("test"))
        self.source.refresh_from_db()
        self.assertEqual(self.source.consecutive_failures, 1)
        self.assertEqual(self.source.status, "error")
        self.assertEqual(self.source.last_error, "test")

    def test_auto_pause_at_threshold(self):
        """Status set to paused when failures >= threshold."""
        self.source.consecutive_failures = 4
        self.source.save()
        mark_source_error(self.source, Exception("test"))
        self.source.refresh_from_db()
        self.assertEqual(self.source.consecutive_failures, 5)
        self.assertEqual(self.source.status, "paused")


class IngestSourceTest(TestCase):
    """Test ingest_source function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.source = Source.objects.create(
            workspace=self.workspace,
            name="Test",
            provider_type="rss",
            status="healthy",
        )

    def test_provider_exception_marks_error(self):
        """Provider exception increments failure and marks error."""
        with patch("canopyresearch.services.ingestion.get_provider_class") as mock_get:
            mock_get.side_effect = RuntimeError("Provider broken")
            with self.assertRaises(RuntimeError):
                ingest_source(self.source)
            self.source.refresh_from_db()
            self.assertEqual(self.source.status, "error")
            self.assertEqual(self.source.consecutive_failures, 1)

    def test_skips_invalid_documents(self):
        """Invalid documents (e.g., missing URL) are skipped with warning."""
        from unittest.mock import Mock

        mock_provider = Mock()
        mock_provider.fetch.return_value = [
            {"id": "1", "title": "Valid", "link": "https://example.com/1"},
            {"id": "2", "title": "Invalid", "link": ""},  # Empty URL
            {"id": "3", "title": "Valid 2", "link": "https://example.com/3"},
        ]
        mock_provider.normalize.side_effect = [
            {
                "external_id": "1",
                "title": "Valid",
                "url": "https://example.com/1",
                "content": "Content 1",
                "published_at": timezone.now(),
            },
            {
                "external_id": "2",
                "title": "Invalid",
                "url": "",  # Empty URL should be rejected
                "content": "Content 2",
                "published_at": timezone.now(),
            },
            {
                "external_id": "3",
                "title": "Valid 2",
                "url": "https://example.com/3",
                "content": "Content 3",
                "published_at": timezone.now(),
            },
        ]

        # Mock provider class to return our mock_provider when instantiated
        mock_provider_class = Mock(return_value=mock_provider)
        with patch("canopyresearch.services.ingestion.get_provider_class") as mock_get:
            mock_get.return_value = mock_provider_class
            found, created = ingest_source(self.source)

        # Should find 3 documents but only create 2 (invalid one skipped)
        self.assertEqual(found, 3)
        self.assertEqual(created, 2)
        self.assertEqual(Document.objects.filter(workspace=self.workspace).count(), 2)
        # Verify valid documents were created
        self.assertTrue(
            Document.objects.filter(workspace=self.workspace, url="https://example.com/1").exists()
        )
        self.assertTrue(
            Document.objects.filter(workspace=self.workspace, url="https://example.com/3").exists()
        )
        # Verify invalid document was not created
        self.assertFalse(
            Document.objects.filter(workspace=self.workspace, external_id="2").exists()
        )
