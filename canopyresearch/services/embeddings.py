"""
Embedding service for canopyresearch.

Provides a swappable interface for computing document embeddings, with local
and optional cloud backends.
"""

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


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


class LocalEmbeddingBackend(EmbeddingBackend):
    """
    Local embedding backend using sentence-transformers.

    Uses CPU by default. Model can be configured via EMBEDDING_MODEL env var.
    Default model: 'all-mpnet-base-v2' (optimized for document similarity and clustering).
    See EMBEDDING_MODELS.md for model selection guidance and tradeoffs.
    """

    def __init__(self, model_name: str | None = None):
        """
        Initialize the local embedding backend.

        Args:
            model_name: Name of the sentence-transformers model to use.
                       Defaults to 'all-mpnet-base-v2' (768 dimensions).
                       See EMBEDDING_MODELS.md for model selection guidance.
        """
        self._model_name = model_name or os.environ.get("EMBEDDING_MODEL", "all-mpnet-base-v2")
        self._model = None
        self._embedding_dim_cache: int | None = None

    def _get_model(self):
        """Lazy-load the sentence-transformers model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model: %s", self._model_name)
                self._model = SentenceTransformer(self._model_name)
                logger.info("Embedding model loaded successfully")
            except ImportError as e:
                raise RuntimeError(
                    "sentence-transformers is required for local embeddings. "
                    "Install it with: pip install sentence-transformers"
                ) from e
        return self._model

    @property
    def embedding_dim(self) -> int:
        """Return the dimension of embeddings."""
        if self._embedding_dim_cache is None:
            # Get dimension by embedding a dummy text
            model = self._get_model()
            dummy_embedding = model.encode(["dummy"], show_progress_bar=False)[0]
            self._embedding_dim_cache = len(dummy_embedding)
        return self._embedding_dim_cache

    @property
    def model_name(self) -> str:
        """Return the model identifier."""
        return f"local:{self._model_name}"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings using sentence-transformers."""
        if not texts:
            return []

        model = self._get_model()
        # Filter out empty texts
        non_empty_texts = [text if text else " " for text in texts]
        embeddings = model.encode(non_empty_texts, show_progress_bar=False, convert_to_numpy=True)
        # Convert numpy arrays to list of lists of floats
        # This ensures JSON serializability for Django JSONField
        result = []
        for emb in embeddings:
            # Handle numpy arrays, PyTorch tensors, or lists
            if hasattr(emb, "tolist"):
                # numpy array - convert to list then to floats
                result.append([float(x) for x in emb.tolist()])
            elif hasattr(emb, "cpu") and hasattr(emb, "numpy"):
                # PyTorch tensor - convert to numpy then to list
                result.append([float(x) for x in emb.cpu().numpy().tolist()])
            else:
                # already a list or iterable
                result.append([float(x) for x in emb])
        return result


class CloudEmbeddingBackend(EmbeddingBackend):
    """
    Cloud embedding backend (optional, configurable).

    Supports OpenAI, Anthropic, or other cloud providers via environment variables.
    """

    def __init__(self, provider: str | None = None, api_key: str | None = None):
        """
        Initialize the cloud embedding backend.

        Args:
            provider: Provider name ('openai', 'anthropic', etc.)
            api_key: API key (if not provided, reads from env vars)
        """
        self._provider = provider or os.environ.get("EMBEDDING_CLOUD_PROVIDER", "openai")
        self._api_key = api_key or os.environ.get("EMBEDDING_CLOUD_API_KEY")
        self._model_name_override = os.environ.get("EMBEDDING_CLOUD_MODEL")
        self._embedding_dim_cache: int | None = None

        if not self._api_key:
            raise ValueError(
                f"API key required for cloud embedding backend ({self._provider}). "
                "Set EMBEDDING_CLOUD_API_KEY environment variable."
            )

    @property
    def embedding_dim(self) -> int:
        """Return the dimension of embeddings."""
        if self._embedding_dim_cache is None:
            # Default dimensions by provider
            dims = {
                "openai": 1536,  # text-embedding-ada-002
                "anthropic": 1024,  # Example, adjust based on actual model
            }
            self._embedding_dim_cache = dims.get(self._provider, 1536)
        return self._embedding_dim_cache

    @property
    def model_name(self) -> str:
        """Return the model identifier."""
        model = self._model_name_override or {
            "openai": "text-embedding-ada-002",
        }.get(self._provider, "unknown")
        return f"cloud:{self._provider}:{model}"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings using cloud API."""
        if not texts:
            return []

        if self._provider == "openai":
            return self._embed_openai(texts)
        else:
            raise ValueError(f"Unsupported cloud provider: {self._provider}")

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using OpenAI API."""
        try:
            import openai

            client = openai.OpenAI(api_key=self._api_key)
            model = self._model_name_override or "text-embedding-ada-002"

            # Filter out empty texts
            non_empty_texts = [text if text else " " for text in texts]

            response = client.embeddings.create(input=non_empty_texts, model=model)
            return [list(item.embedding) for item in response.data]
        except ImportError as e:
            raise RuntimeError(
                "openai package is required for OpenAI embeddings. Install with: pip install openai"
            ) from e


def get_embedding_backend() -> EmbeddingBackend:
    """
    Get the configured embedding backend.

    Checks environment variables:
    - EMBEDDING_BACKEND: 'local' (default) or 'cloud'
    - For cloud: EMBEDDING_CLOUD_PROVIDER, EMBEDDING_CLOUD_API_KEY

    Returns:
        Configured EmbeddingBackend instance
    """
    backend_type = os.environ.get("EMBEDDING_BACKEND", "local").lower()

    if backend_type == "cloud":
        provider = os.environ.get("EMBEDDING_CLOUD_PROVIDER", "openai")
        api_key = os.environ.get("EMBEDDING_CLOUD_API_KEY")
        return CloudEmbeddingBackend(provider=provider, api_key=api_key)
    else:
        model_name = os.environ.get("EMBEDDING_MODEL")
        return LocalEmbeddingBackend(model_name=model_name)
