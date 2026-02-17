"""
Tests for canopyresearch background tasks.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from canopyresearch.models import Document, Source, Workspace
from canopyresearch.tasks import fetch_workspace_sources

User = get_user_model()


class FetchWorkspaceSourcesTest(TestCase):
    """Test fetch_workspace_sources task."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    def test_fetch_workspace_sources_nonexistent(self):
        """Test fetching sources for non-existent workspace."""
        result = fetch_workspace_sources(99999)
        self.assertEqual(result["sources_processed"], 0)
        self.assertEqual(result["errors"], 0)

    def test_fetch_workspace_sources_no_sources(self):
        """Test fetching sources when workspace has no sources."""
        result = fetch_workspace_sources(self.workspace.id)
        self.assertEqual(result["sources_processed"], 0)
        self.assertEqual(result["documents_fetched"], 0)
        self.assertEqual(result["documents_saved"], 0)

    def test_fetch_workspace_sources_only_healthy(self):
        """Test that only healthy sources are processed."""
        Source.objects.create(
            workspace=self.workspace,
            name="Healthy Source",
            provider_type="rss",
            status="healthy",
        )
        Source.objects.create(
            workspace=self.workspace,
            name="Paused Source",
            provider_type="rss",
            status="paused",
        )

        with patch("canopyresearch.tasks.get_provider_class") as mock_get_provider:
            mock_provider_class = MagicMock()
            mock_provider = MagicMock()
            mock_provider.fetch_documents.return_value = []
            mock_provider_class.return_value = mock_provider
            mock_get_provider.return_value = mock_provider_class

            result = fetch_workspace_sources(self.workspace.id)

            # Should only process healthy source
            self.assertEqual(result["sources_processed"], 1)
            # Should only be called once (for healthy source)
            self.assertEqual(mock_get_provider.call_count, 1)

    def test_fetch_workspace_sources_saves_documents(self):
        """Test that fetched documents are saved."""
        Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
            status="healthy",
        )

        test_documents = [
            {
                "title": "Test Article",
                "url": "https://example.com/article",
                "content": "Test content",
                "published_at": timezone.now(),
                "metadata": {},
            }
        ]

        with patch("canopyresearch.tasks.get_provider_class") as mock_get_provider:
            mock_provider_class = MagicMock()
            mock_provider = MagicMock()
            mock_provider.fetch_documents.return_value = test_documents
            mock_provider_class.return_value = mock_provider
            mock_get_provider.return_value = mock_provider_class

            result = fetch_workspace_sources(self.workspace.id)

            self.assertEqual(result["sources_processed"], 1)
            self.assertEqual(result["documents_fetched"], 1)
            self.assertEqual(result["documents_saved"], 1)

            # Verify document was saved
            self.assertTrue(
                Document.objects.filter(
                    workspace=self.workspace, url="https://example.com/article"
                ).exists()
            )

    def test_fetch_workspace_sources_updates_last_fetched(self):
        """Test that source last_fetched is updated after successful fetch."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
            status="healthy",
        )
        initial_last_fetched = source.last_fetched

        with patch("canopyresearch.tasks.get_provider_class") as mock_get_provider:
            mock_provider_class = MagicMock()
            mock_provider = MagicMock()
            mock_provider.fetch_documents.return_value = []
            mock_provider_class.return_value = mock_provider
            mock_get_provider.return_value = mock_provider_class

            fetch_workspace_sources(self.workspace.id)

            source.refresh_from_db()
            self.assertIsNotNone(source.last_fetched)
            if initial_last_fetched:
                self.assertGreater(source.last_fetched, initial_last_fetched)

    def test_fetch_workspace_sources_handles_errors(self):
        """Test that errors are handled gracefully."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
            status="healthy",
        )

        with patch("canopyresearch.tasks.get_provider_class") as mock_get_provider:
            mock_get_provider.side_effect = Exception("Provider error")

            result = fetch_workspace_sources(self.workspace.id)

            self.assertEqual(result["sources_processed"], 0)
            self.assertEqual(result["errors"], 1)

            # Source status should be updated to error
            source.refresh_from_db()
            self.assertEqual(source.status, "error")
