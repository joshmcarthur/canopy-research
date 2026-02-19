"""
Workspace core centroid management service.

Handles seeding, feedback, and centroid updates for workspace cores.
"""

import logging

import numpy as np
from django.db import transaction
from django.utils import timezone

from canopyresearch.models import Document, Workspace, WorkspaceCoreFeedback, WorkspaceCoreSeed
from canopyresearch.services.utils import cosine_similarity

logger = logging.getLogger(__name__)


def compute_centroid(embeddings: list[list[float]]) -> list[float]:
    """
    Compute the centroid (mean) of a list of embedding vectors.

    Args:
        embeddings: List of embedding vectors (each is a list of floats)

    Returns:
        Centroid vector as a list of floats
    """
    if not embeddings:
        return []

    # Convert to numpy array for efficient computation
    arr = np.array(embeddings)
    centroid = np.mean(arr, axis=0)
    return centroid.tolist()


def seed_workspace_core(workspace: Workspace, num_seeds: int = 5) -> list[Document]:
    """
    Seed a workspace core by finding top-K documents matching workspace name/description.

    Args:
        workspace: Workspace to seed
        num_seeds: Number of seed documents to select

    Returns:
        List of seeded Document objects
    """
    from canopyresearch.services.embeddings import get_embedding_backend

    # Build query text from workspace name and description
    query_text = f"{workspace.name} {workspace.description}".strip()
    if not query_text:
        logger.warning("Workspace %s has no name/description for seeding", workspace.id)
        return []

    # Get embedding backend
    backend = get_embedding_backend()

    # Embed the query
    query_embedding = backend.embed_texts([query_text])[0]

    # Find documents with embeddings in this workspace
    # Filter at the database level for portability and efficiency across databases
    documents_with_embeddings = workspace.documents.filter(
        embedding__isnull=False
    ).exclude(embedding=[])
    if not documents_with_embeddings:
        logger.info("No documents with embeddings found for workspace %s", workspace.id)
        return []

    # Compute similarities and select top-K
    similarities = []
    for doc in documents_with_embeddings:
        similarity = cosine_similarity(query_embedding, doc.embedding)
        similarities.append((similarity, doc))

    # Sort by similarity (descending) and take top-K
    similarities.sort(key=lambda x: x[0], reverse=True)
    selected_docs = [doc for _, doc in similarities[:num_seeds]]

    # Mark as seeds
    with transaction.atomic():
        for doc in selected_docs:
            WorkspaceCoreSeed.objects.get_or_create(
                workspace=workspace, document=doc, defaults={"seed_source": "auto"}
            )

    logger.info("Seeded %d documents for workspace %s", len(selected_docs), workspace.id)
    return selected_docs


def update_workspace_core_centroid(workspace: Workspace) -> list[float] | None:
    """
    Update workspace core centroid from feedback events.

    Uses positively-weighted documents (thumbs up) and subtracts downvotes.

    Args:
        workspace: Workspace to update

    Returns:
        Updated centroid vector or None if no valid documents
    """
    # Get all feedback events, ordered by creation time
    feedback_events = (
        WorkspaceCoreFeedback.objects.filter(workspace=workspace)
        .select_related("document")
        .order_by("created_at")
    )

    # Build weighted document list
    # We'll use the most recent vote per document
    document_weights: dict[int, float] = {}
    for feedback in feedback_events:
        doc_id = feedback.document_id
        weight = 1.0 if feedback.vote == "up" else -0.5  # Downvotes have negative weight
        document_weights[doc_id] = weight  # Most recent vote wins

    # Also include seed documents (if they have embeddings)
    seed_docs = WorkspaceCoreSeed.objects.filter(workspace=workspace).select_related("document")
    for seed in seed_docs:
        if seed.document_id not in document_weights:
            document_weights[seed.document_id] = 1.0  # Seeds have positive weight

    # Collect embeddings with weights
    # Fetch all required documents in a single query to avoid N+1 lookups
    documents = Document.objects.filter(pk__in=list(document_weights.keys()))
    documents_by_id = {doc.id: doc for doc in documents}

    weighted_embeddings: list[tuple[list[float], float]] = []
    for doc_id, weight in document_weights.items():
        doc = documents_by_id.get(doc_id)
        if not doc:
            continue
        if doc.embedding and isinstance(doc.embedding, list) and len(doc.embedding) > 0:
            weighted_embeddings.append((doc.embedding, weight))

    if not weighted_embeddings:
        logger.warning("No valid embeddings found for workspace %s core centroid", workspace.id)
        return None

    # Compute weighted centroid
    if len(weighted_embeddings) == 1:
        # Single embedding, just return it (weighted)
        vec, weight = weighted_embeddings[0]
        if weight < 0:
            # Negative weight, return empty centroid
            return None
        return vec

    # Multiple embeddings: compute weighted mean
    embeddings_list = [emb for emb, _ in weighted_embeddings]
    weights_list = [w for _, w in weighted_embeddings]

    # Normalize weights to sum to 1 (but keep sign)
    total_abs_weight = sum(abs(w) for w in weights_list)
    if total_abs_weight == 0:
        return None

    normalized_weights = [w / total_abs_weight for w in weights_list]

    # Compute weighted centroid
    arr = np.array(embeddings_list)
    weights_arr = np.array(normalized_weights).reshape(-1, 1)
    weighted_centroid = np.sum(arr * weights_arr, axis=0)
    centroid = weighted_centroid.tolist()

    # Update workspace
    workspace.core_centroid = {"vector": centroid, "updated_at": timezone.now().isoformat()}
    workspace.save(update_fields=["core_centroid", "updated_at"])

    logger.info(
        "Updated core centroid for workspace %s (from %d documents)",
        workspace.id,
        len(weighted_embeddings),
    )
    return centroid


def add_core_feedback(
    workspace: Workspace, document: Document, vote: str, user=None
) -> WorkspaceCoreFeedback:
    """
    Add a feedback event (thumbs up/down) and update the core centroid.

    Args:
        workspace: Workspace
        document: Document being voted on
        vote: 'up' or 'down'
        user: Optional user who provided feedback

    Returns:
        Created WorkspaceCoreFeedback instance
    """
    if vote not in ["up", "down"]:
        raise ValueError(f"Invalid vote: {vote}. Must be 'up' or 'down'")

    # Ensure document has an embedding
    if (
        not document.embedding
        or not isinstance(document.embedding, list)
        or len(document.embedding) == 0
    ):
        raise ValueError(f"Document {document.id} does not have an embedding. Process it first.")

    # Create feedback event
    feedback = WorkspaceCoreFeedback.objects.create(
        workspace=workspace, document=document, vote=vote, user=user
    )

    # Update centroid
    update_workspace_core_centroid(workspace)

    logger.info(
        "Added %s feedback for document %s in workspace %s", vote, document.id, workspace.id
    )
    return feedback
