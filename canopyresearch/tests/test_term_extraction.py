"""
Tests for term extraction service.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from canopyresearch.models import Document, Workspace, WorkspaceCoreFeedback
from canopyresearch.services.term_extraction import (
    extract_terms_from_document,
    extract_terms_from_text,
    extract_terms_with_llm,
)

User = get_user_model()


class TermExtractionTest(TestCase):
    """Test term extraction functions."""

    def test_extract_terms_from_text_simple(self):
        """Test simple text extraction."""
        text = "Machine learning research on distributed systems"
        terms = extract_terms_from_text(text)

        # Should extract meaningful terms
        self.assertIn("machine", terms)
        self.assertIn("learning", terms)
        self.assertIn("distributed", terms)
        self.assertIn("systems", terms)

        # Should filter stopwords
        self.assertNotIn("on", terms)
        self.assertNotIn("the", terms)

    def test_extract_terms_from_text_empty(self):
        """Test extraction with empty text."""
        self.assertEqual(extract_terms_from_text(""), [])
        self.assertEqual(extract_terms_from_text("   "), [])

    def test_extract_terms_from_text_min_length(self):
        """Test minimum length filtering."""
        text = "a an the it ML AI"
        terms = extract_terms_from_text(text, min_length=2)

        # Should filter single-letter words
        self.assertNotIn("a", terms)
        self.assertNotIn("an", terms)
        # But keep valid 2+ letter words
        self.assertIn("ml", terms)
        self.assertIn("ai", terms)

    def test_extract_terms_from_document(self):
        """Test extraction from document."""
        user = User.objects.create_user(username="testuser", email="test@example.com")
        workspace = Workspace.objects.create(
            name="Test Workspace",
            owner=user,
        )
        document = Document.objects.create(
            workspace=workspace,
            title="Research on Python programming",
            content="This document discusses Python programming and machine learning.",
            url="https://example.com/doc",
        )

        terms = extract_terms_from_document(document, use_llm=False)

        # Should extract from title and content
        self.assertIn("research", terms)
        self.assertIn("python", terms)
        self.assertIn("programming", terms)
        # Title terms should appear first
        self.assertEqual(terms[0], "research")

    def test_extract_terms_from_document_llm_fallback(self):
        """Test LLM extraction falls back to simple extraction."""
        user = User.objects.create_user(username="testuser", email="test@example.com")
        workspace = Workspace.objects.create(
            name="Test Workspace",
            owner=user,
        )
        document = Document.objects.create(
            workspace=workspace,
            title="Machine learning research",
            content="Deep learning and neural networks",
            url="https://example.com/doc",
        )

        # Mock LLM to fail
        with patch("canopyresearch.services.term_extraction.extract_terms_with_llm") as mock_llm:
            mock_llm.side_effect = Exception("LLM unavailable")

            terms = extract_terms_from_document(document, use_llm=True)

            # Should fall back to simple extraction
            self.assertIn("machine", terms)
            self.assertIn("learning", terms)

    def test_extract_terms_with_llm_no_api_key(self):
        """Without an API key, falls back to simple extraction."""
        import os

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            terms = extract_terms_with_llm("Research on machine learning and neural networks")

        self.assertIn("machine", terms)
        self.assertIn("learning", terms)

    def test_extract_terms_with_llm_api(self):
        """With an API key, calls the OpenAI-compatible client."""
        import os
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices[
            0
        ].message.content = '["machine learning", "neural networks", "deep learning"]'

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=mock_client):
                terms = extract_terms_with_llm("Research on machine learning")

        self.assertIn("machine learning", terms)
        self.assertIn("neural networks", terms)
        mock_client.chat.completions.create.assert_called_once()

    def test_extract_terms_with_llm_api_failure_fallback(self):
        """API failure falls back to simple extraction."""
        import os

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("openai.OpenAI", side_effect=Exception("Connection failed")):
                terms = extract_terms_with_llm("Machine learning research")

        self.assertIn("machine", terms)
        self.assertIn("learning", terms)

    def test_extract_terms_from_text_punctuation(self):
        """Test that punctuation is handled correctly."""
        text = "Python, JavaScript, and TypeScript are languages."
        terms = extract_terms_from_text(text)

        # Should remove punctuation
        self.assertIn("python", terms)
        self.assertIn("javascript", terms)
        self.assertIn("typescript", terms)
        self.assertIn("languages", terms)

    def test_extract_terms_from_text_case_insensitive(self):
        """Test that extraction is case-insensitive."""
        text = "Machine Learning RESEARCH"
        terms = extract_terms_from_text(text)

        # Should all be lowercase
        self.assertIn("machine", terms)
        self.assertIn("learning", terms)
        self.assertIn("research", terms)

        # Should be deduplicated
        self.assertEqual(terms.count("machine"), 1)
        self.assertEqual(terms.count("learning"), 1)


class TermExtractionIntegrationTest(TestCase):
    """Integration tests for term extraction with models."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.workspace = Workspace.objects.create(
            owner=self.user,
            name="Machine Learning Research",
            description="Research on deep learning and neural networks",
        )

    def test_extract_terms_from_workspace_context(self):
        """Test extracting terms from workspace name and description."""
        # Initialize terms
        from canopyresearch.services.source_discovery import (
            extract_search_terms,
            initialize_workspace_search_terms,
        )

        initialize_workspace_search_terms(self.workspace, use_llm=False)

        # Extract combined terms
        terms = extract_search_terms(self.workspace)

        # Should include terms from name and description
        self.assertIn("machine", terms)
        self.assertIn("learning", terms)
        self.assertIn("deep", terms)
        self.assertIn("neural", terms)

    def test_extract_terms_from_document_feedback(self):
        """Test extracting terms from thumbs-up documents."""
        from canopyresearch.services.source_discovery import (
            extract_search_terms,
            update_search_terms_from_feedback,
        )

        # Create a document
        document = Document.objects.create(
            workspace=self.workspace,
            title="Python Machine Learning",
            content="Using scikit-learn for machine learning tasks",
            url="https://example.com/doc",
        )

        # Create feedback
        WorkspaceCoreFeedback.objects.create(
            workspace=self.workspace,
            document=document,
            vote="up",
            user=self.user,
        )

        # Update search terms from feedback
        update_search_terms_from_feedback(self.workspace, document, use_llm=False)

        # Extract combined terms
        terms = extract_search_terms(self.workspace)

        # Should include terms from document
        self.assertIn("python", terms)
        self.assertIn("machine", terms)
        self.assertIn("learning", terms)

    def test_term_weights(self):
        """Test that terms are weighted correctly."""
        # Initialize workspace terms
        from canopyresearch.services.source_discovery import (
            extract_search_terms,
            initialize_workspace_search_terms,
        )

        initialize_workspace_search_terms(self.workspace, use_llm=False)

        # Create document with overlapping terms
        document = Document.objects.create(
            workspace=self.workspace,
            title="Machine Learning",
            content="Machine learning research",
            url="https://example.com/doc",
        )

        # Add feedback
        WorkspaceCoreFeedback.objects.create(
            workspace=self.workspace,
            document=document,
            vote="up",
            user=self.user,
        )

        # Update terms
        from canopyresearch.services.source_discovery import update_search_terms_from_feedback

        update_search_terms_from_feedback(self.workspace, document, use_llm=False)

        # Extract terms (should be weighted)
        terms = extract_search_terms(self.workspace)

        # "machine" and "learning" should appear (from both workspace and document)
        self.assertIn("machine", terms)
        self.assertIn("learning", terms)
