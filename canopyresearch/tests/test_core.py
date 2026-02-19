"""
Tests for workspace core centroid management.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from canopyresearch.models import Document, Workspace, WorkspaceCoreSeed
from canopyresearch.services.core import (
    add_core_feedback,
    compute_centroid,
    seed_workspace_core,
    update_workspace_core_centroid,
)
from canopyresearch.services.utils import cosine_similarity

User = get_user_model()


class CoreServiceTest(TestCase):
    """Test core centroid management."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(
            name="Test Workspace", description="Test description", owner=self.user
        )

    def test_compute_centroid(self):
        """Test centroid computation."""
        embeddings = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]
        centroid = compute_centroid(embeddings)
        self.assertEqual(len(centroid), 3)
        self.assertAlmostEqual(centroid[0], 4.0, places=1)

    def test_cosine_similarity(self):
        """Test cosine similarity computation."""
        vec1 = [1.0, 0.0]
        vec2 = [1.0, 0.0]
        similarity = cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(similarity, 1.0, places=5)

        vec3 = [0.0, 1.0]
        similarity = cosine_similarity(vec1, vec3)
        self.assertAlmostEqual(similarity, 0.0, places=5)

    def test_update_workspace_core_centroid_no_documents(self):
        """Test updating centroid with no documents."""
        centroid = update_workspace_core_centroid(self.workspace)
        self.assertIsNone(centroid)

    def test_add_core_feedback(self):
        """Test adding feedback."""
        # Create document with embedding
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Test Doc",
            url="http://example.com",
            content="Test content",
            embedding=[0.1] * 384,  # Mock embedding
        )

        feedback = add_core_feedback(self.workspace, doc, "up", user=self.user)
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback.vote, "up")
        self.assertEqual(feedback.document, doc)

        # Verify feedback was created (centroid update happens in background task)
        self.assertEqual(self.workspace.core_feedback.count(), 1)

        # Manually update centroid to verify the feedback is used correctly
        centroid = update_workspace_core_centroid(self.workspace)
        self.assertIsNotNone(centroid)
        self.workspace.refresh_from_db()
        self.assertIsNotNone(self.workspace.core_centroid)

    @patch("canopyresearch.services.embeddings.get_embedding_backend")
    def test_seed_workspace_core(self, mock_get_backend):
        """Test seeding workspace core."""
        # Create documents with embeddings
        for i in range(10):
            Document.objects.create(
                workspace=self.workspace,
                title=f"Doc {i}",
                url=f"http://example.com/{i}",
                content=f"Content {i}",
                embedding=[float(i)] * 384,  # Mock embeddings
            )

        # Mock embedding backend
        mock_backend = MagicMock()
        # Return a query embedding that will match documents
        mock_backend.embed_texts.return_value = [[0.5] * 384]
        mock_get_backend.return_value = mock_backend

        seeded = seed_workspace_core(self.workspace, num_seeds=5)
        self.assertEqual(len(seeded), 5)
        self.assertEqual(WorkspaceCoreSeed.objects.filter(workspace=self.workspace).count(), 5)
