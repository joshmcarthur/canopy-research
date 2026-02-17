"""
Tests for canopyresearch views.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from canopyresearch.models import Source, Workspace

User = get_user_model()


class WorkspaceCreateViewTest(TestCase):
    """Test workspace create view (root route)."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    def test_workspace_create_requires_login(self):
        """Test that workspace create requires login."""
        self.client.logout()
        with self.assertRaises(User.DoesNotExist):
            self.client.get(reverse("workspace_create"))

    def test_workspace_create_renders(self):
        """Test that workspace create form renders correctly."""
        response = self.client.get(reverse("workspace_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What can I help you with?")

    def test_workspace_create_post_creates_workspace(self):
        """Test that POST creates a workspace and redirects."""
        response = self.client.post(
            reverse("workspace_create"),
            {"name": "New Workspace", "description": "Test description"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Workspace.objects.filter(name="New Workspace").exists())

    def test_workspace_create_shows_success_message(self):
        """Test that workspace creation shows success message."""
        response = self.client.post(
            reverse("workspace_create"),
            {"name": "New Workspace", "description": "Test description"},
            follow=True,
        )
        messages_list = list(messages.get_messages(response.wsgi_request))
        self.assertEqual(len(messages_list), 1)
        self.assertEqual(messages_list[0].tags, "success")
        self.assertIn("New Workspace", str(messages_list[0]))

    def test_authenticated_header_renders(self):
        """Test that header with workspace switcher dropdown and brandmark renders for authenticated users."""
        response = self.client.get(reverse("workspace_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "workspace-switcher")
        self.assertContains(response, "Canopy")
        self.assertContains(response, "sl-dropdown")
        self.assertContains(response, "New workspace")


class WorkspaceDetailViewTest(TestCase):
    """Test workspace detail view."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    def test_workspace_detail_renders(self):
        """Test that workspace detail redirects to sources tab and renders."""
        response = self.client.get(reverse("workspace_detail", args=[self.workspace.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("source_list", args=[self.workspace.id]))
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Workspace")

    def test_workspace_detail_requires_ownership(self):
        """Test that workspace detail requires ownership."""
        other_user = User.objects.create_user(username="otheruser", password="testpass")
        other_workspace = Workspace.objects.create(name="Other Workspace", owner=other_user)

        response = self.client.get(reverse("workspace_detail", args=[other_workspace.id]))
        self.assertEqual(response.status_code, 404)


class WorkspaceIngestViewTest(TestCase):
    """Test workspace ingest view."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)

    def test_workspace_ingest_post_triggers_task(self):
        """Test that POST triggers ingestion task."""
        response = self.client.post(
            reverse("workspace_ingest", args=[self.workspace.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ingesting")

    def test_workspace_ingest_requires_ownership(self):
        """Test that ingest requires workspace ownership."""
        other_user = User.objects.create_user(username="otheruser", password="testpass")
        other_workspace = Workspace.objects.create(name="Other", owner=other_user)
        response = self.client.post(reverse("workspace_ingest", args=[other_workspace.id]))
        self.assertEqual(response.status_code, 404)


class WorkspaceSwitchViewTest(TestCase):
    """Test workspace switch HTMX view."""

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
    def test_workspace_switch_requires_login(self):
        """Test that workspace switch requires login."""
        self.client.logout()
        response = self.client.get(reverse("workspace_switch", args=[self.workspace.id]))
        # @login_required redirects unauthenticated users to login page
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/accounts/login/"))

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

    def test_source_create_htmx_returns_modal_partial(self):
        """Test that source create GET with HTMX returns form partial for modal."""
        response = self.client.get(
            reverse("source_create", args=[self.workspace.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Source")
        self.assertContains(response, "resource-dialog")

    def test_source_create_htmx_post_success_returns_trigger_headers(self):
        """Test that source create POST with HTMX returns closeDialog trigger on success."""
        response = self.client.post(
            reverse("source_create", args=[self.workspace.id]),
            {
                "name": "New Source",
                "provider_type": "rss",
                "config_json": '{"url": "https://example.com/feed.xml"}',
                "status": "healthy",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Trigger", response)
        self.assertIn("closeDialog", response["HX-Trigger"])
        self.assertTrue(Source.objects.filter(name="New Source").exists())

    def test_source_create_shows_success_message(self):
        """Test that source creation shows success message."""
        response = self.client.post(
            reverse("source_create", args=[self.workspace.id]),
            {
                "name": "New Source",
                "provider_type": "rss",
                "config_json": '{"url": "https://example.com/feed.xml"}',
                "status": "healthy",
            },
            follow=True,
        )
        messages_list = list(messages.get_messages(response.wsgi_request))
        self.assertEqual(len(messages_list), 1)
        self.assertEqual(messages_list[0].tags, "success")
        self.assertIn("New Source", str(messages_list[0]))

    def test_source_edit_shows_success_message(self):
        """Test that source edit shows success message."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        response = self.client.post(
            reverse("source_edit", args=[self.workspace.id, source.id]),
            {
                "name": "Updated Source",
                "provider_type": "rss",
                "config_json": "{}",
                "status": "healthy",
            },
            follow=True,
        )
        messages_list = list(messages.get_messages(response.wsgi_request))
        self.assertEqual(len(messages_list), 1)
        self.assertEqual(messages_list[0].tags, "success")
        self.assertIn("Updated Source", str(messages_list[0]))

    def test_source_delete_shows_success_message(self):
        """Test that source delete shows success message."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        response = self.client.post(
            reverse("source_delete", args=[self.workspace.id, source.id]),
            {},
            follow=True,
        )
        messages_list = list(messages.get_messages(response.wsgi_request))
        self.assertEqual(len(messages_list), 1)
        self.assertEqual(messages_list[0].tags, "success")
        self.assertIn("Test Source", str(messages_list[0]))

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

    def test_source_list_htmx_returns_partial(self):
        """Test that source list returns partial when HX-Request header present."""
        response = self.client.get(
            reverse("source_list", args=[self.workspace.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "workspace_detail")
        self.assertNotContains(response, "<html")

    def test_document_list_htmx_returns_partial(self):
        """Test that document list returns partial when HX-Request header present."""
        response = self.client.get(
            reverse("document_list", args=[self.workspace.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")

    def test_source_edit_htmx_returns_modal_partial(self):
        """Test that source edit GET with HTMX returns form partial for modal."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        response = self.client.get(
            reverse("source_edit", args=[self.workspace.id, source.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Source")
        self.assertContains(response, "resource-dialog")

    def test_source_delete_get_htmx_returns_confirm_partial(self):
        """Test that source delete GET with HTMX returns confirm dialog partial."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        response = self.client.get(
            reverse("source_delete", args=[self.workspace.id, source.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Source")
        self.assertContains(response, "Delete")

    def test_source_edit_htmx_post_success_returns_trigger_headers(self):
        """Test that source edit POST with HTMX returns closeDialog trigger on success."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        response = self.client.post(
            reverse("source_edit", args=[self.workspace.id, source.id]),
            {
                "name": "Updated Source",
                "provider_type": "rss",
                "config_json": "{}",
                "status": "healthy",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Trigger", response)
        self.assertIn("closeDialog", response["HX-Trigger"])

    def test_source_delete_htmx_post_success_returns_trigger_headers(self):
        """Test that source delete POST with HTMX returns closeDialog trigger on success."""
        source = Source.objects.create(
            workspace=self.workspace,
            name="Test Source",
            provider_type="rss",
        )
        response = self.client.post(
            reverse("source_delete", args=[self.workspace.id, source.id]),
            {},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Trigger", response)
        self.assertIn("closeDialog", response["HX-Trigger"])
        self.assertFalse(Source.objects.filter(id=source.id).exists())

    def test_source_edit_requires_ownership(self):
        """Test that source edit returns 404 for source in other user's workspace."""
        other_user = User.objects.create_user(username="otheruser", password="testpass")
        other_workspace = Workspace.objects.create(name="Other", owner=other_user)
        source = Source.objects.create(
            workspace=other_workspace,
            name="Other Source",
            provider_type="rss",
        )
        response = self.client.get(
            reverse("source_edit", args=[other_workspace.id, source.id]),
        )
        self.assertEqual(response.status_code, 404)

    def test_source_delete_requires_ownership(self):
        """Test that source delete returns 404 for source in other user's workspace."""
        other_user = User.objects.create_user(username="otheruser", password="testpass")
        other_workspace = Workspace.objects.create(name="Other", owner=other_user)
        source = Source.objects.create(
            workspace=other_workspace,
            name="Other Source",
            provider_type="rss",
        )
        response = self.client.post(
            reverse("source_delete", args=[other_workspace.id, source.id]),
            {},
        )
        self.assertEqual(response.status_code, 404)
