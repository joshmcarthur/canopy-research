"""
Tests for canopyresearch background tasks.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from canopyresearch.models import Document, Source, Workspace
from canopyresearch.tasks import task_ingest_workspace

User = get_user_model()


class TaskIngestWorkspaceTest(TestCase):
    """Test task_ingest_workspace task."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    def test_task_ingest_workspace_nonexistent(self):
        """Test ingesting for non-existent workspace."""
        result = task_ingest_workspace.enqueue(workspace_id=99999)
        self.assertEqual(result.return_value["sources_processed"], 0)
        self.assertEqual(result.return_value["errors"], 0)

    def test_task_ingest_workspace_no_sources(self):
        """Test ingesting when workspace has no sources."""
        result = task_ingest_workspace.enqueue(workspace_id=self.workspace.id)
        self.assertEqual(result.return_value["sources_processed"], 0)
        self.assertEqual(result.return_value["documents_fetched"], 0)
        self.assertEqual(result.return_value["documents_saved"], 0)

    def test_task_ingest_workspace_only_healthy(self):
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

        with patch("canopyresearch.services.ingestion.get_provider_class") as mock_get:
            mock_provider_class = MagicMock()
            mock_provider = MagicMock()
            mock_provider.fetch.return_value = []
            mock_provider_class.return_value = mock_provider
            mock_get.return_value = mock_provider_class

            result = task_ingest_workspace.enqueue(workspace_id=self.workspace.id)

            self.assertEqual(result.return_value["sources_processed"], 1)
            self.assertEqual(mock_get.call_count, 1)

    def test_task_ingest_workspace_saves_documents(self):
        """Test that fetched documents are saved."""
        Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
            status="healthy",
        )

        raw_doc = {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "Content",
        }
        normalized = {
            "external_id": None,
            "title": "Test Article",
            "url": "https://example.com/article",
            "content": "Content",
            "published_at": timezone.now(),
            "metadata": {},
        }

        with patch("canopyresearch.services.ingestion.get_provider_class") as mock_get:
            mock_provider_class = MagicMock()
            mock_provider = MagicMock()
            mock_provider.fetch.return_value = [raw_doc]
            mock_provider.normalize.return_value = normalized
            mock_provider_class.return_value = mock_provider
            mock_get.return_value = mock_provider_class

            result = task_ingest_workspace.enqueue(workspace_id=self.workspace.id)

            self.assertEqual(result.return_value["sources_processed"], 1)
            self.assertEqual(result.return_value["documents_fetched"], 1)
            self.assertEqual(result.return_value["documents_saved"], 1)
            self.assertTrue(
                Document.objects.filter(
                    workspace=self.workspace, url="https://example.com/article"
                ).exists()
            )

    def test_task_ingest_workspace_updates_last_fetched(self):
        """Test that source last_successful_fetch is updated after successful fetch."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
            status="healthy",
        )

        with patch("canopyresearch.services.ingestion.get_provider_class") as mock_get:
            mock_provider_class = MagicMock()
            mock_provider = MagicMock()
            mock_provider.fetch.return_value = []
            mock_provider_class.return_value = mock_provider
            mock_get.return_value = mock_provider_class

            task_ingest_workspace.enqueue(workspace_id=self.workspace.id)

            source.refresh_from_db()
            self.assertIsNotNone(source.last_successful_fetch)

    def test_task_ingest_workspace_handles_errors(self):
        """Test that errors are handled gracefully."""
        Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
            status="healthy",
        )

        with patch("canopyresearch.services.ingestion.get_provider_class") as mock_get:
            mock_get.side_effect = Exception("Provider error")

            result = task_ingest_workspace.enqueue(workspace_id=self.workspace.id)

            self.assertEqual(result.return_value["sources_processed"], 0)
            self.assertEqual(result.return_value["errors"], 1)

            source = Source.objects.get(workspace=self.workspace)
            source.refresh_from_db()
            self.assertEqual(source.status, "error")
