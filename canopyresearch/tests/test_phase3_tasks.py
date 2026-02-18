"""
Tests for Phase 3 background tasks.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from canopyresearch.models import Document, Workspace
from canopyresearch.tasks import (
    task_assign_cluster,
    task_extract_and_embed_document,
    task_process_document,
    task_score_document,
    task_update_workspace_core,
)

User = get_user_model()


class Phase3TasksTest(TestCase):
    """Test Phase 3 background tasks."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(
            name="Test Workspace", description="Test", owner=self.user
        )

    @patch("canopyresearch.tasks.get_embedding_backend")
    def test_task_extract_and_embed_document(self, mock_get_backend):
        """Test document extraction and embedding task."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Test Doc",
            url="http://example.com",
            content="Test content",
        )

        # Mock embedding backend
        mock_backend = MagicMock()
        mock_backend.embed_texts.return_value = [[0.1] * 384]
        mock_backend.model_name = "test-model"
        mock_backend.embedding_dim = 384
        mock_get_backend.return_value = mock_backend

        result = task_extract_and_embed_document.enqueue(document_id=doc.id)
        self.assertEqual(result.return_value["status"], "success")

        doc.refresh_from_db()
        self.assertEqual(len(doc.embedding), 384)

    def test_task_assign_cluster(self):
        """Test cluster assignment task."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Test Doc",
            url="http://example.com",
            content="Test content",
            embedding=[0.1] * 384,
        )

        result = task_assign_cluster.enqueue(document_id=doc.id)
        self.assertEqual(result.return_value["status"], "success")
        self.assertIn("cluster_id", result.return_value)

    def test_task_score_document(self):
        """Test document scoring task."""
        self.workspace.core_centroid = {"vector": [0.1] * 384}
        self.workspace.save()

        doc = Document.objects.create(
            workspace=self.workspace,
            title="Test Doc",
            url="http://example.com",
            content="Test content",
            embedding=[0.1] * 384,
        )

        result = task_score_document.enqueue(document_id=doc.id)
        self.assertEqual(result.return_value["status"], "success")
        self.assertIn("scores", result.return_value)
        self.assertIn("alignment", result.return_value["scores"])

    @patch("canopyresearch.services.embeddings.get_embedding_backend")
    def test_task_update_workspace_core(self, mock_get_backend):
        """Test workspace core update task."""
        # Create documents with embeddings
        for i in range(5):
            Document.objects.create(
                workspace=self.workspace,
                title=f"Doc {i}",
                url=f"http://example.com/{i}",
                content=f"Content {i}",
                embedding=[float(i)] * 384,
            )

        # Mock embedding backend for seeding
        mock_backend = MagicMock()
        mock_backend.embed_texts.return_value = [[0.5] * 384]
        mock_get_backend.return_value = mock_backend

        result = task_update_workspace_core.enqueue(workspace_id=self.workspace.id)
        self.assertEqual(result.return_value["status"], "success")

        self.workspace.refresh_from_db()
        self.assertIsNotNone(self.workspace.core_centroid)

    @patch("canopyresearch.tasks.task_extract_and_embed_document")
    @patch("canopyresearch.tasks.task_assign_cluster")
    @patch("canopyresearch.tasks.task_score_document")
    def test_task_process_document(self, mock_score, mock_cluster, mock_embed):
        """Test full document processing pipeline."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Test Doc",
            url="http://example.com",
            content="Test content",
        )

        # Create mock TaskResult objects
        mock_embed_result = MagicMock()
        mock_embed_result.return_value = {"status": "success"}
        mock_embed.enqueue = MagicMock(return_value=mock_embed_result)

        mock_cluster_result = MagicMock()
        mock_cluster_result.return_value = {"status": "success", "cluster_id": 1}
        mock_cluster.enqueue = MagicMock(return_value=mock_cluster_result)

        mock_score_result = MagicMock()
        mock_score_result.return_value = {"status": "success", "scores": {}}
        mock_score.enqueue = MagicMock(return_value=mock_score_result)

        result = task_process_document.enqueue(document_id=doc.id)
        self.assertEqual(result.return_value["status"], "success")
        self.assertIn("results", result.return_value)
