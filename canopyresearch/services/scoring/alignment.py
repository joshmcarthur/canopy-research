"""
Alignment scoring service.

Computes how well a document aligns with the workspace core centroid.
"""

import logging

from canopyresearch.models import Document, Workspace
from canopyresearch.services.utils import cosine_similarity

logger = logging.getLogger(__name__)


def compute_alignment_score(document: Document, workspace: Workspace | None = None) -> float:
    """
    Compute alignment score between document and workspace core.

    Args:
        document: Document to score
        workspace: Workspace (if None, uses document.workspace)

    Returns:
        Alignment score between -1 and 1 (cosine similarity)
    """
    if workspace is None:
        workspace = document.workspace

    if (
        not document.embedding
        or not isinstance(document.embedding, list)
        or len(document.embedding) == 0
    ):
        logger.debug("Document %s has no embedding, returning 0 alignment", document.id)
        return 0.0

    core_centroid = workspace.core_centroid
    if not core_centroid or not isinstance(core_centroid, dict):
        logger.debug("Workspace %s has no core centroid, returning 0 alignment", workspace.id)
        return 0.0

    core_vector = core_centroid.get("vector")
    if not core_vector or not isinstance(core_vector, list) or len(core_vector) == 0:
        logger.debug(
            "Workspace %s core centroid has no vector, returning 0 alignment", workspace.id
        )
        return 0.0

    # Compute cosine similarity
    similarity = cosine_similarity(document.embedding, core_vector)
    return float(similarity)
