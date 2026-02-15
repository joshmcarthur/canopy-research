"""
Basic tests for the canopyresearch project.
"""

from django.test import TestCase


class BasicTests(TestCase):
    """Basic smoke tests."""

    def test_django_setup(self):
        """Test that Django is properly configured."""
        from django.conf import settings

        self.assertTrue(settings.configured)
        self.assertEqual(settings.ROOT_URLCONF, "canopyresearch.urls")
