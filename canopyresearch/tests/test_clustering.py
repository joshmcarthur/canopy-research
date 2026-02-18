"""
Tests for clustering service.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from canopyresearch.models import Cluster, ClusterMembership, Document, Workspace
from canopyresearch.services.clustering import (
    assign_document_to_cluster,
    compute_cluster_centroid,
    reconcile_cluster_centroids,
)

User = get_user_model()


class ClusteringServiceTest(TestCase):
    """Test clustering service."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(
            name="Test Workspace", description="Test", owner=self.user
        )

    def test_assign_document_to_cluster_new(self):
        """Test assigning document to new cluster."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Test Doc",
            url="http://example.com",
            content="Test content",
            embedding=[0.1] * 384,
        )

        cluster = assign_document_to_cluster(doc)
        self.assertIsNotNone(cluster)
        self.assertEqual(cluster.size, 1)
        self.assertTrue(ClusterMembership.objects.filter(document=doc, cluster=cluster).exists())

    def test_assign_document_to_cluster_existing(self):
        """Test assigning document to existing cluster."""
        # Create cluster
        cluster = Cluster.objects.create(workspace=self.workspace, centroid=[0.1] * 384, size=1)
        doc1 = Document.objects.create(
            workspace=self.workspace,
            title="Doc 1",
            url="http://example.com/1",
            content="Content 1",
            embedding=[0.1] * 384,
        )
        ClusterMembership.objects.create(document=doc1, cluster=cluster)

        # Create similar document
        doc2 = Document.objects.create(
            workspace=self.workspace,
            title="Doc 2",
            url="http://example.com/2",
            content="Content 2",
            embedding=[0.11] * 384,  # Very similar
        )

        assigned_cluster = assign_document_to_cluster(doc2, threshold=0.7)
        self.assertEqual(assigned_cluster.id, cluster.id)
        self.assertEqual(cluster.memberships.count(), 2)

    def test_compute_cluster_centroid(self):
        """Test computing cluster centroid."""
        cluster = Cluster.objects.create(workspace=self.workspace, centroid=[], size=0)
        doc1 = Document.objects.create(
            workspace=self.workspace,
            title="Doc 1",
            url="http://example.com/1",
            content="Content 1",
            embedding=[1.0, 2.0, 3.0],
        )
        doc2 = Document.objects.create(
            workspace=self.workspace,
            title="Doc 2",
            url="http://example.com/2",
            content="Content 2",
            embedding=[4.0, 5.0, 6.0],
        )
        ClusterMembership.objects.create(document=doc1, cluster=cluster)
        ClusterMembership.objects.create(document=doc2, cluster=cluster)

        centroid = compute_cluster_centroid(cluster)
        self.assertIsNotNone(centroid)
        self.assertEqual(len(centroid), 3)
        self.assertAlmostEqual(centroid[0], 2.5, places=1)

    def test_reconcile_cluster_centroids(self):
        """Test reconciling cluster centroids."""
        cluster = Cluster.objects.create(workspace=self.workspace, centroid=[0.0] * 384, size=0)
        doc = Document.objects.create(
            workspace=self.workspace,
            title="Doc",
            url="http://example.com",
            content="Content",
            embedding=[0.1] * 384,
        )
        ClusterMembership.objects.create(document=doc, cluster=cluster)

        reconcile_cluster_centroids(workspace=self.workspace)
        cluster.refresh_from_db()
        self.assertEqual(cluster.size, 1)
        self.assertEqual(len(cluster.centroid), 384)
