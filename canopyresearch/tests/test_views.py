"""
Tests for canopyresearch views.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from canopyresearch.models import Source, Workspace

User = get_user_model()


class WorkspaceListViewTest(TestCase):
    """Test workspace list view."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    @override_settings(
        MIDDLEWARE=[
            m for m in settings.MIDDLEWARE if m != "canopyresearch.middleware.AutoLoginMiddleware"
        ]
    )
    def test_workspace_list_requires_login(self):
        """Test that workspace list requires login."""
        self.client.logout()
        response = self.client.get(reverse("workspace_list"))
        # @login_required redirects unauthenticated users to login page
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/accounts/login/"))

    def test_workspace_list_renders(self):
        """Test that workspace list renders correctly."""
        response = self.client.get(reverse("workspace_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Workspace")

    def test_workspace_list_only_shows_user_workspaces(self):
        """Test that workspace list only shows workspaces owned by user."""
        other_user = User.objects.create_user(username="otheruser", password="testpass")
        Workspace.objects.create(name="Other Workspace", owner=other_user)

        response = self.client.get(reverse("workspace_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Workspace")
        self.assertNotContains(response, "Other Workspace")


class WorkspaceDetailViewTest(TestCase):
    """Test workspace detail view."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    def test_workspace_detail_renders(self):
        """Test that workspace detail renders correctly."""
        response = self.client.get(reverse("workspace_detail", args=[self.workspace.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Workspace")

    def test_workspace_detail_requires_ownership(self):
        """Test that workspace detail requires ownership."""
        other_user = User.objects.create_user(username="otheruser", password="testpass")
        other_workspace = Workspace.objects.create(name="Other Workspace", owner=other_user)

        response = self.client.get(reverse("workspace_detail", args=[other_workspace.id]))
        self.assertEqual(response.status_code, 404)


class WorkspaceSwitchViewTest(TestCase):
    """Test workspace switch HTMX view."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    def test_workspace_switch_renders(self):
        """Test that workspace switch renders partial content."""
        response = self.client.get(reverse("workspace_switch", args=[self.workspace.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Workspace")


class SourceCRUDViewTest(TestCase):
    """Test source CRUD views."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    def test_source_list_renders(self):
        """Test that source list renders correctly."""
        Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
            config={"url": "https://example.com/feed.xml"},
        )
        response = self.client.get(reverse("source_list", args=[self.workspace.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Source")

    def test_source_create_get(self):
        """Test source create form renders."""
        response = self.client.get(reverse("source_create", args=[self.workspace.id]))
        self.assertEqual(response.status_code, 200)

    def test_source_create_post(self):
        """Test creating a source via POST."""
        response = self.client.post(
            reverse("source_create", args=[self.workspace.id]),
            {
                "name": "New Source",
                "provider_type": "rss",
                "config_json": '{"url": "https://example.com/feed.xml"}',
                "status": "healthy",
            },
        )
        self.assertEqual(response.status_code, 302)  # Redirect after creation
        self.assertTrue(Source.objects.filter(name="New Source").exists())

    def test_source_edit_renders(self):
        """Test source edit form renders."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        response = self.client.get(reverse("source_edit", args=[self.workspace.id, source.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Source")

    def test_source_delete(self):
        """Test deleting a source."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        response = self.client.post(reverse("source_delete", args=[self.workspace.id, source.id]))
        self.assertEqual(response.status_code, 302)  # Redirect after deletion
        self.assertFalse(Source.objects.filter(id=source.id).exists())
