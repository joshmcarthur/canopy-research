"""
Tests for canopyresearch models.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from canopyresearch.models import Document, DocumentSource, Source, Workspace

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
            title="Test Document",
            url="https://example.com/article",
            content="Test content",
            published_at=timezone.now(),
        )
        # Associate document with source
        DocumentSource.objects.create(document=document, source=self.source)

        self.assertEqual(document.title, "Test Document")
        self.assertEqual(document.url, "https://example.com/article")
        self.assertEqual(document.workspace, self.workspace)
        self.assertIn(self.source, document.sources.all())
        self.assertTrue(
            document.content_hash or document.title
        )  # content_hash from ingestion or empty

    def test_document_deduplication(self):
        """Test document deduplication via content_hash at workspace level."""
        from django.db import IntegrityError
        from django.utils import timezone

        content_hash = "a" * 64  # Deterministic hash for deduplication

        # Create first document with content_hash
        doc1 = Document.objects.create(
            workspace=self.workspace,
            title="Test Document",
            url="https://example.com/article",
            content="Test content",
            published_at=timezone.now(),
            content_hash=content_hash,
        )
        DocumentSource.objects.create(document=doc1, source=self.source)

        # Creating second document with same content_hash should fail
        with self.assertRaises(IntegrityError):
            Document.objects.create(
                workspace=self.workspace,
                title="Test Document",
                url="https://example.com/article",
                content="Different content",
                published_at=timezone.now(),
                content_hash=content_hash,
            )

    def test_document_same_hash_different_sources(self):
        """Test that same document (same content_hash) from different sources shares the same document instance."""
        from django.utils import timezone

        content_hash = "b" * 64

        # Create second source in the same workspace
        source2 = Source.objects.create(
            workspace=self.workspace,
            name="Another Source",
            provider_type="hackernews",
        )

        # Create first document from first source
        doc1 = Document.objects.create(
            workspace=self.workspace,
            title="Test Document",
            url="https://example.com/article",
            content="Test content",
            published_at=timezone.now(),
            content_hash=content_hash,
        )
        DocumentSource.objects.create(document=doc1, source=self.source)

        # Get or create same document (same content_hash) from different source
        doc2, created = Document.objects.get_or_create(
            workspace=self.workspace,
            content_hash=content_hash,
            defaults={
                "title": "Test Document",
                "url": "https://example.com/article",
                "content": "Test content",
                "published_at": timezone.now(),
            },
        )

        # Should be the same document instance (not created)
        self.assertFalse(created)
        self.assertEqual(doc1.id, doc2.id)

        # Associate the document with the second source
        DocumentSource.objects.get_or_create(document=doc2, source=source2)

        # Document should now be associated with both sources
        self.assertEqual(doc1.sources.count(), 2)
        self.assertIn(self.source, doc1.sources.all())
        self.assertIn(source2, doc1.sources.all())

        # Only one document should exist
        self.assertEqual(
            Document.objects.filter(workspace=self.workspace, content_hash=content_hash).count(), 1
        )

    def test_document_str(self):
        """Test document string representation."""
        from django.utils import timezone

        document = Document.objects.create(
            workspace=self.workspace,
            title="Test Document",
            url="https://example.com/article",
            content="Test content",
            published_at=timezone.now(),
        )
        # Associate document with source
        DocumentSource.objects.create(document=document, source=self.source)

        self.assertEqual(str(document), "Test Document")
