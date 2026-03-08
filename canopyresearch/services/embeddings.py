"""
Embedding service for canopyresearch.

Uses an OpenAI-compatible embeddings API. Configure via environment variables:

    OPENAI_API_KEY   — required; use any non-empty string for local servers
    OPENAI_API_BASE  — base URL (default: https://api.openai.com/v1)
    EMBEDDING_MODEL  — model name (default: text-embedding-3-small)

Any OpenAI-compatible server works: OpenAI, Ollama, LM Studio, vLLM, etc.
"""

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "text-embedding-3-small"


class EmbeddingBackend(ABC):
    """Abstract base class for embedding backends."""

    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Return the dimension of embeddings produced by this backend."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return a human-readable name/identifier for this backend."""
        raise NotImplementedError

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Compute embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each is a list of floats)
        """
        raise NotImplementedError


class OpenAIEmbeddingBackend(EmbeddingBackend):
    """
    Embedding backend using any OpenAI-compatible embeddings API.

    Works with OpenAI, Ollama, LM Studio, vLLM, and other compatible servers.
    Configure via OPENAI_API_KEY, OPENAI_API_BASE, and EMBEDDING_MODEL env vars.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._api_base = api_base or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        self._model = model or os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL)
        self._embedding_dim_cache: int | None = None

        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for embeddings. "
                "Set it to your API key, or to any non-empty string for local servers."
            )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def embedding_dim(self) -> int:
        if self._embedding_dim_cache is None:
            # Probe dimension with a single embedding
            probe = self.embed_texts(["probe"])
            self._embedding_dim_cache = len(probe[0]) if probe else 0
        return self._embedding_dim_cache

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings via the OpenAI-compatible API."""
        if not texts:
            return []

        import openai

        client = openai.OpenAI(api_key=self._api_key, base_url=self._api_base)
        # Replace empty strings with a single space — the API rejects empty inputs
        inputs = [text if text and text.strip() else " " for text in texts]

        response = client.embeddings.create(input=inputs, model=self._model)
        # Response items are ordered by index, matching input order
        return [list(item.embedding) for item in response.data]


def get_embedding_backend() -> EmbeddingBackend:
    """
    Return a configured embedding backend.

    Reads OPENAI_API_KEY, OPENAI_API_BASE, and EMBEDDING_MODEL from the environment.
    Raises RuntimeError if OPENAI_API_KEY is not set.
    """
    return OpenAIEmbeddingBackend()
