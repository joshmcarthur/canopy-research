"""
Tests for canopyresearch models.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from canopyresearch.models import Document, Source, Workspace

User = get_user_model()


class WorkspaceModelTest(TestCase):
    """Test Workspace model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")

    def test_workspace_creation(self):
        """Test creating a workspace."""
        workspace = Workspace.objects.create(
            name="Test Workspace",
            description="Test description",
            owner=self.user,
        )
        self.assertEqual(workspace.name, "Test Workspace")
        self.assertEqual(workspace.description, "Test description")
        self.assertEqual(workspace.owner, self.user)
        self.assertIsNotNone(workspace.created_at)
        self.assertIsNotNone(workspace.updated_at)

    def test_workspace_str(self):
        """Test workspace string representation."""
        workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.assertEqual(str(workspace), "Test Workspace")

    def test_workspace_relationships(self):
        """Test workspace relationships."""
        workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        source = Source.objects.create(
            workspace=workspace,
            name="Test Source",
            provider_type="rss",
            config={"url": "https://example.com/feed.xml"},
        )
        self.assertEqual(workspace.sources.count(), 1)
        self.assertEqual(source.workspace, workspace)


class SourceModelTest(TestCase):
    """Test Source model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    def test_source_creation(self):
        """Test creating a source."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
            config={"url": "https://example.com/feed.xml"},
        )
        self.assertEqual(source.name, "Test Source")
        self.assertEqual(source.provider_type, "rss")
        self.assertEqual(source.workspace, self.workspace)
        self.assertEqual(source.status, "healthy")

    def test_source_str(self):
        """Test source string representation."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        self.assertIn("Test Source", str(source))
        self.assertIn("RSS Feed", str(source))

    def test_source_unique_per_workspace(self):
        """Test that source names are unique per workspace."""
        Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        # Creating another source with the same name in the same workspace should fail
        with self.assertRaises(IntegrityError):
            Source.objects.create(
                workspace=self.workspace,
                name="Test Source",
                provider_type="hackernews",
            )

    def test_source_different_workspaces_same_name(self):
        """Test that sources can have the same name in different workspaces."""
        workspace2 = Workspace.objects.create(name="Workspace 2", owner=self.user)
        Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        # Should be able to create source with same name in different workspace
        source2 = Source.objects.create(
            workspace=workspace2,
            name="Test Source",
            provider_type="rss",
        )
        self.assertEqual(source2.name, "Test Source")


class DocumentModelTest(TestCase):
    """Test Document model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        self.source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )

    def test_document_creation(self):
        """Test creating a document."""
        from django.utils import timezone

        document = Document.objects.create(
            workspace=self.workspace,
            source=self.source,
            title="Test Document",
            url="https://example.com/article",
            content="Test content",
            published_at=timezone.now(),
        )
        self.assertEqual(document.title, "Test Document")
        self.assertEqual(document.url, "https://example.com/article")
        self.assertEqual(document.workspace, self.workspace)
        self.assertEqual(document.source, self.source)
        self.assertIsNotNone(document.hash)

    def test_document_hash_generation(self):
        """Test that document hash is automatically generated."""
        from django.utils import timezone

        document = Document.objects.create(
            workspace=self.workspace,
            source=self.source,
            title="Test Document",
            url="https://example.com/article",
            content="Test content",
            published_at=timezone.now(),
        )
        self.assertIsNotNone(document.hash)
        self.assertEqual(len(document.hash), 64)  # SHA-256 hex digest length

    def test_document_deduplication(self):
        """Test document deduplication via hash."""
        from django.db import IntegrityError
        from django.utils import timezone

        # Create first document
        doc1 = Document.objects.create(
            workspace=self.workspace,
            source=self.source,
            title="Test Document",
            url="https://example.com/article",
            content="Test content",
            published_at=timezone.now(),
        )
        hash1 = doc1.hash

        # Creating second document with same URL and title should fail due to unique constraint
        # (when hash is not empty, which it won't be since we generate it)
        with self.assertRaises(IntegrityError):
            Document.objects.create(
                workspace=self.workspace,
                source=self.source,
                title="Test Document",
                url="https://example.com/article",
                content="Different content",
                published_at=timezone.now(),
            )

        # Verify hash was generated
        self.assertIsNotNone(hash1)
        self.assertEqual(len(hash1), 64)  # SHA-256 hex digest length

    def test_document_str(self):
        """Test document string representation."""
        from django.utils import timezone

        document = Document.objects.create(
            workspace=self.workspace,
            source=self.source,
            title="Test Document",
            url="https://example.com/article",
            content="Test content",
            published_at=timezone.now(),
        )
        self.assertEqual(str(document), "Test Document")
