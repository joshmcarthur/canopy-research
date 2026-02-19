"""
Tests for embedding service.
"""

import os
from unittest.mock import MagicMock, patch

from django.test import TestCase

from canopyresearch.services.embeddings import LocalEmbeddingBackend, get_embedding_backend


class EmbeddingServiceTest(TestCase):
    """Test embedding backends."""

    def test_local_backend_embedding_dim(self):
        """Test that local backend returns correct embedding dimension."""
        backend = LocalEmbeddingBackend(model_name="all-MiniLM-L6-v2")
        # Mock the model to avoid loading it
        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.1] * 384]  # 384-dim vector
        backend._model = mock_model

        dim = backend.embedding_dim
        self.assertEqual(dim, 384)

    def test_local_backend_embed_texts(self):
        """Test embedding texts."""
        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        backend._model = mock_model

        embeddings = backend.embed_texts(["text1", "text2"])
        self.assertEqual(len(embeddings), 2)
        self.assertEqual(len(embeddings[0]), 3)

    def test_get_embedding_backend_default(self):
        """Test getting default (local) backend."""
        with patch.dict(os.environ, {}, clear=False):
            backend = get_embedding_backend()
            self.assertIsInstance(backend, LocalEmbeddingBackend)
            # Verify default model is all-mpnet-base-v2
            self.assertEqual(backend.model_name, "local:all-mpnet-base-v2")
