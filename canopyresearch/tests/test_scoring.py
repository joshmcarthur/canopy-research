"""
Tests for scoring services.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from canopyresearch.models import Cluster, Document, Workspace
from canopyresearch.services.scoring import (
    compute_alignment_score,
    compute_cluster_velocity_score,
    compute_novelty_score,
    compute_velocity_score,
)

User = get_user_model()


class ScoringServiceTest(TestCase):
    """Test scoring services."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(
            name="Test Workspace", description="Test", owner=self.user
        )
        # Set up core centroid
        self.workspace.core_centroid = {"vector": [0.1] * 384}
        self.workspace.save()

    def test_compute_alignment_score(self):
        """Test alignment score computation."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Test Doc",
            url="http://example.com",
            content="Test content",
            embedding=[0.1] * 384,  # Similar to core
        )

        score = compute_alignment_score(doc)
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_compute_novelty_score_no_clusters(self):
        """Test novelty score with no clusters."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Test Doc",
            url="http://example.com",
            content="Test content",
            embedding=[0.1] * 384,
        )

        score = compute_novelty_score(doc)
        self.assertEqual(score, 1.0)  # Maximally novel when no clusters

    def test_compute_novelty_score_with_clusters(self):
        """Test novelty score with existing clusters."""
        # Create cluster
        Cluster.objects.create(workspace=self.workspace, centroid=[0.1] * 384, size=1)

        # Document similar to cluster
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Test Doc",
            url="http://example.com",
            content="Test content",
            embedding=[0.11] * 384,  # Very similar
        )

        score = compute_novelty_score(doc)
        self.assertLess(score, 1.0)  # Less novel when similar to cluster

    def test_compute_velocity_score(self):
        """Test velocity score computation."""
        # Recent document
        recent_doc = Document.objects.create(
            workspace=self.workspace,
            title="Recent Doc",
            url="http://example.com/recent",
            content="Content",
            published_at=timezone.now() - timedelta(days=1),
        )

        score = compute_velocity_score(recent_doc, days_window=7)
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)

        # Old document
        old_doc = Document.objects.create(
            workspace=self.workspace,
            title="Old Doc",
            url="http://example.com/old",
            content="Content",
            published_at=timezone.now() - timedelta(days=30),
        )

        score = compute_velocity_score(old_doc, days_window=7)
        self.assertEqual(score, 0.0)

    def test_compute_cluster_velocity_score(self):
        """Test cluster velocity score."""
        cluster = Cluster.objects.create(workspace=self.workspace, centroid=[0.1] * 384, size=0)

        # Add recent membership
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Doc",
            url="http://example.com",
            content="Content",
            embedding=[0.1] * 384,
        )
        from canopyresearch.models import ClusterMembership

        ClusterMembership.objects.create(document=doc, cluster=cluster)

        score = compute_cluster_velocity_score(cluster, days_window=7)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
