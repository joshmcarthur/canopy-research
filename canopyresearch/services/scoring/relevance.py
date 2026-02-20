"""
Relevance scoring service.

Computes combined relevance score from alignment, velocity, and optional bias terms.
"""

import logging

from canopyresearch.models import Document, WorkspaceCoreFeedback

logger = logging.getLogger(__name__)

# Default weights for relevance computation
# These can be tuned based on user feedback
ALIGNMENT_WEIGHT = 0.70
VELOCITY_WEIGHT = 0.20
BIAS_WEIGHT = 0.10


def normalize_alignment(alignment: float) -> float:
    """
    Normalize cosine similarity alignment (-1 to 1) to 0-1 range.

    Args:
        alignment: Raw cosine similarity (-1 to 1)

    Returns:
        Normalized alignment (0 to 1)
    """
    return max(0.0, min(1.0, (alignment + 1.0) / 2.0))


def compute_feedback_bias(document: Document, workspace) -> float:
    """
    Compute feedback bias based on user votes.

    Args:
        document: Document to compute bias for
        workspace: Workspace context

    Returns:
        Bias score between 0 and 1 (default 0.5 for neutral)
    """
    # Get most recent feedback for this document in this workspace
    feedback = (
        WorkspaceCoreFeedback.objects.filter(workspace=workspace, document=document)
        .order_by("-created_at")
        .first()
    )

    if not feedback:
        return 0.5  # Neutral bias if no feedback

    # Upvote = 1.0, downvote = 0.0
    return 1.0 if feedback.vote == "up" else 0.0


def compute_source_weight(document: Document) -> float:
    """
    Compute source weight for a document (average of all source weights).

    Args:
        document: Document to compute source weight for

    Returns:
        Average source weight (default 1.0)
    """
    sources = document.sources.all()
    if not sources:
        return 1.0

    total_weight = sum(source.weight for source in sources)
    return total_weight / len(sources)


def compute_relevance_score(
    document: Document,
    workspace=None,
    alignment_weight: float = ALIGNMENT_WEIGHT,
    velocity_weight: float = VELOCITY_WEIGHT,
    bias_weight: float = BIAS_WEIGHT,
) -> float:
    """
    Compute combined relevance score for a document.

    Formula: relevance = alignment_weight * align_norm + velocity_weight * velocity + bias_weight * bias

    Args:
        document: Document to score
        workspace: Workspace (if None, uses document.workspace)
        alignment_weight: Weight for alignment component (default 0.70)
        velocity_weight: Weight for velocity component (default 0.20)
        bias_weight: Weight for bias component (default 0.10)

    Returns:
        Relevance score between 0 and 1
    """
    if workspace is None:
        workspace = document.workspace

    # Get component scores (must be computed first)
    alignment = document.alignment
    velocity = document.velocity

    if alignment is None or velocity is None:
        logger.debug(
            "Document %s missing alignment or velocity scores, returning 0 relevance",
            document.id,
        )
        return 0.0

    # Normalize alignment
    align_norm = normalize_alignment(alignment)

    # Compute bias (feedback + source weight)
    feedback_bias = compute_feedback_bias(document, workspace)
    source_weight = compute_source_weight(document)
    # Combine feedback and source weight (source weight modulates feedback)
    bias = feedback_bias * source_weight

    # Compute weighted relevance
    relevance = alignment_weight * align_norm + velocity_weight * velocity + bias_weight * bias

    # Clamp to 0-1
    relevance = max(0.0, min(1.0, relevance))

    return float(relevance)
