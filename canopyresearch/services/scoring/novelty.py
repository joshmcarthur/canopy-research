"""
Novelty scoring service.

Computes how novel a document is compared to existing clusters.
Redesigned to avoid self-cluster suppression by excluding the document's assigned cluster.
"""

import logging

from canopyresearch.models import Cluster, Document
from canopyresearch.services.utils import cosine_similarity

logger = logging.getLogger(__name__)


def compute_novelty_score(document: Document) -> float:
    """
    Compute novelty score: distance from nearest cluster centroid, excluding assigned cluster.

    Higher score = more novel (farther from existing clusters).
    Score is 1 - similarity to nearest cluster (so 1.0 = completely novel).

    This version excludes the document's assigned cluster to avoid the "self-cluster"
    problem where a document in its own single-doc cluster has novelty ~0.

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

    # Get the document's assigned cluster (if any)
    assigned_cluster_id = None
    membership = document.cluster_memberships.first()
    if membership:
        assigned_cluster_id = membership.cluster_id

    # Find nearest cluster (excluding assigned cluster)
    best_similarity = -1.0
    for cluster in clusters:
        # Skip assigned cluster to avoid self-cluster suppression
        if cluster.id == assigned_cluster_id:
            continue

        if (
            not cluster.centroid
            or not isinstance(cluster.centroid, list)
            or len(cluster.centroid) == 0
        ):
            continue

        similarity = cosine_similarity(document.embedding, cluster.centroid)
        if similarity > best_similarity:
            best_similarity = similarity

    # If no other clusters exist (only assigned cluster), document is maximally novel
    if best_similarity < 0:
        return 1.0

    # Novelty = 1 - similarity (so high similarity = low novelty)
    novelty = 1.0 - max(0.0, best_similarity)
    return float(novelty)
