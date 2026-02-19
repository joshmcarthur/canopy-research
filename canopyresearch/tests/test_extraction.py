"""
Tests for content extraction service.
"""

from django.test import TestCase

from canopyresearch.services.extraction import clean_text, extract_html_to_text, normalize_text


class ExtractionServiceTest(TestCase):
    """Test content extraction and cleaning."""

    def test_normalize_text(self):
        """Test text normalization."""
        # Multiple spaces
        self.assertEqual(normalize_text("hello    world"), "hello world")
        # Multiple newlines
        self.assertEqual(normalize_text("hello\n\n\nworld"), "hello\n\nworld")
        # Leading/trailing whitespace
        self.assertEqual(normalize_text("  hello  "), "hello")

    def test_clean_text(self):
        """Test text cleaning with length limit."""
        text = "This is a test " * 100  # Long text
        cleaned = clean_text(text, max_length=50)
        self.assertLessEqual(len(cleaned), 53)  # Allow for "..."
        self.assertTrue(cleaned.endswith("...") or len(cleaned) <= 50)

    def test_extract_html_to_text(self):
        """Test HTML to text extraction."""
        html = "<html><body><p>Hello <b>world</b></p></body></html>"
        text = extract_html_to_text(html)
        self.assertIsNotNone(text)
        self.assertIn("Hello", text)
        self.assertIn("world", text)

    def test_extract_html_to_text_empty(self):
        """Test extraction with empty HTML."""
        self.assertIsNone(extract_html_to_text(""))
        self.assertIsNone(extract_html_to_text("<html></html>"))
