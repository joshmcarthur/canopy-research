"""
Tests for embedding service.
"""

import os
from unittest.mock import MagicMock, patch

from django.test import TestCase

from canopyresearch.services.embeddings import OpenAIEmbeddingBackend, get_embedding_backend


class EmbeddingBackendTest(TestCase):
    """Test the OpenAI-compatible embedding backend."""

    def _make_backend(self, model="text-embedding-3-small"):
        return OpenAIEmbeddingBackend(
            api_key="test-key",
            api_base="https://api.openai.com/v1",
            model=model,
        )

    def _mock_response(self, vectors):
        """Build a mock OpenAI embeddings response."""
        mock_resp = MagicMock()
        mock_resp.data = [MagicMock(embedding=v) for v in vectors]
        return mock_resp

    def test_embed_texts_returns_vectors(self):
        """embed_texts calls the API and returns float lists."""
        backend = self._make_backend()
        vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value.embeddings.create.return_value = self._mock_response(vectors)
            result = backend.embed_texts(["hello", "world"])

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [0.1, 0.2, 0.3])

    def test_embed_texts_empty_input(self):
        """embed_texts returns [] for empty input without calling the API."""
        backend = self._make_backend()
        with patch("openai.OpenAI") as mock_cls:
            result = backend.embed_texts([])
        self.assertEqual(result, [])
        mock_cls.assert_not_called()

    def test_embed_texts_replaces_empty_strings(self):
        """Empty strings are replaced with a single space before sending."""
        backend = self._make_backend()

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value.embeddings.create.return_value = self._mock_response([[0.1]])
            backend.embed_texts([""])

        call_kwargs = mock_cls.return_value.embeddings.create.call_args
        inputs = call_kwargs[1]["input"] if call_kwargs[1] else call_kwargs[0][0]
        self.assertEqual(inputs, [" "])

    def test_embedding_dim_probes_api(self):
        """embedding_dim embeds a probe text and caches the dimension."""
        backend = self._make_backend()

        with patch("openai.OpenAI") as mock_cls:
            mock_cls.return_value.embeddings.create.return_value = self._mock_response(
                [[0.1] * 1536]
            )
            dim = backend.embedding_dim

        self.assertEqual(dim, 1536)
        # Second access uses the cache, no extra API call
        _ = backend.embedding_dim
        self.assertEqual(mock_cls.return_value.embeddings.create.call_count, 1)

    def test_model_name_property(self):
        backend = self._make_backend(model="text-embedding-3-small")
        self.assertEqual(backend.model_name, "text-embedding-3-small")

    def test_raises_without_api_key(self):
        """Raises RuntimeError when OPENAI_API_KEY is not configured."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            with self.assertRaises(RuntimeError, msg="OPENAI_API_KEY"):
                OpenAIEmbeddingBackend()

    def test_get_embedding_backend_uses_env(self):
        """get_embedding_backend reads env vars and returns OpenAIEmbeddingBackend."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_API_BASE": "http://localhost:11434/v1",
                "EMBEDDING_MODEL": "nomic-embed-text",
            },
        ):
            backend = get_embedding_backend()

        self.assertIsInstance(backend, OpenAIEmbeddingBackend)
        self.assertEqual(backend.model_name, "nomic-embed-text")

    def test_get_embedding_backend_raises_without_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            with self.assertRaises(RuntimeError):
                get_embedding_backend()
