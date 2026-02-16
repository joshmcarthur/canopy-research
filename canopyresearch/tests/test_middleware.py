"""
Tests for canopyresearch middleware.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class AutoLoginMiddlewareTest(TestCase):
    """Test AutoLoginMiddleware functionality."""

    def setUp(self):
        """Set up test data - ensure admin user exists for most tests."""
        # Create admin user for tests that need it
        User.objects.filter(username="admin").delete()
        admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="admin",
        )
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.save()

    def test_auto_login_fails_when_user_missing(self):
        """Test that middleware raises error when admin user doesn't exist."""
        # Ensure no admin user exists
        User.objects.filter(username="admin").delete()

        # Make request - middleware should raise User.DoesNotExist
        with self.assertRaises(User.DoesNotExist):
            self.client.get("/")

    def test_auto_login_authenticates_user(self):
        """Test that middleware authenticates unauthenticated requests."""
        # Make request without being logged in
        response = self.client.get("/")

        # Verify user is authenticated
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.username, "admin")

    def test_auto_login_preserves_authenticated_user(self):
        """Test that middleware doesn't override already authenticated users."""
        # Create and authenticate a different user
        User.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            password="testpass",
        )
        self.client.login(username="existinguser", password="testpass")

        # Make request - middleware should preserve existing user
        response = self.client.get("/")

        # Verify original user is preserved
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.username, "existinguser")

    def test_middleware_persists_across_requests(self):
        """Test that middleware authentication persists across multiple requests."""
        # First request
        response1 = self.client.get("/admin/")
        self.assertTrue(response1.wsgi_request.user.is_authenticated)
        self.assertEqual(response1.wsgi_request.user.username, "admin")

        # Second request - should still be authenticated
        response2 = self.client.get("/admin/")
        self.assertTrue(response2.wsgi_request.user.is_authenticated)
        self.assertEqual(response2.wsgi_request.user.username, "admin")
