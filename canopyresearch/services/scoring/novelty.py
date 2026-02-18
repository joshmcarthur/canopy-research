"""
Novelty scoring service.

Computes how novel a document is compared to existing clusters.
"""

import logging

from canopyresearch.models import Cluster, Document
from canopyresearch.services.utils import cosine_similarity

logger = logging.getLogger(__name__)


def compute_novelty_score(document: Document) -> float:
    """
    Compute novelty score: distance from nearest cluster centroid.

    Higher score = more novel (farther from existing clusters).
    Score is 1 - similarity to nearest cluster (so 1.0 = completely novel).

    Args:
        document: Document to score

    Returns:
        Novelty score between 0 and 1 (1.0 = completely novel)
    """
    if (
        not document.embedding
        or not isinstance(document.embedding, list)
        or len(document.embedding) == 0
    ):
        logger.debug("Document %s has no embedding, returning 0 novelty", document.id)
        return 0.0

    workspace = document.workspace

    # Find clusters in this workspace
    clusters = Cluster.objects.filter(workspace=workspace).exclude(centroid=[])

    if not clusters.exists():
        # No clusters yet, document is maximally novel
        return 1.0

    # Find nearest cluster
    best_similarity = -1.0
    for cluster in clusters:
        if (
            not cluster.centroid
            or not isinstance(cluster.centroid, list)
            or len(cluster.centroid) == 0
        ):
            continue

        similarity = cosine_similarity(document.embedding, cluster.centroid)
        if similarity > best_similarity:
            best_similarity = similarity

    # Novelty = 1 - similarity (so high similarity = low novelty)
    novelty = 1.0 - max(0.0, best_similarity)
    return float(novelty)
