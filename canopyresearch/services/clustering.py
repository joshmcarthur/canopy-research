"""
Clustering service for canopyresearch.

Handles document-to-cluster assignment and centroid maintenance.
"""

import logging

import numpy as np
from django.db import transaction

from canopyresearch.models import Cluster, ClusterMembership, Document
from canopyresearch.services.utils import cosine_similarity

logger = logging.getLogger(__name__)

# Default similarity threshold for cluster assignment (cosine similarity)
DEFAULT_CLUSTER_THRESHOLD = 0.7


def compute_cluster_centroid(cluster: Cluster) -> list[float] | None:
    """
    Recompute cluster centroid from member document embeddings.

    Args:
        cluster: Cluster to recompute

    Returns:
        Centroid vector or None if no members
    """
    memberships = ClusterMembership.objects.filter(cluster=cluster).select_related("document")
    embeddings = []

    for membership in memberships:
        doc = membership.document
        if doc.embedding and isinstance(doc.embedding, list) and len(doc.embedding) > 0:
            embeddings.append(doc.embedding)

    if not embeddings:
        return None

    # Compute mean
    arr = np.array(embeddings)
    centroid = np.mean(arr, axis=0)
    return centroid.tolist()


def assign_document_to_cluster(
    document: Document, threshold: float = DEFAULT_CLUSTER_THRESHOLD
) -> Cluster | None:
    """
    Assign a document to the nearest cluster, or create a new cluster if none match.

    Args:
        document: Document to assign
        threshold: Minimum cosine similarity to join existing cluster

    Returns:
        Cluster that document was assigned to, or None if document has no embedding
    """
    if (
        not document.embedding
        or not isinstance(document.embedding, list)
        or len(document.embedding) == 0
    ):
        logger.warning("Document %s has no embedding, skipping cluster assignment", document.id)
        return None

    workspace = document.workspace

    # Find existing clusters in this workspace
    clusters = Cluster.objects.filter(workspace=workspace).exclude(centroid=[])

    best_cluster = None
    best_similarity = -1.0

    # Find nearest cluster
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
            best_cluster = cluster

    # Assign to best cluster if above threshold, otherwise create new
    with transaction.atomic():
        if best_cluster and best_similarity >= threshold:
            # Join existing cluster
            ClusterMembership.objects.get_or_create(document=document, cluster=best_cluster)
            # Update cluster size
            best_cluster.size = ClusterMembership.objects.filter(cluster=best_cluster).count()
            # Update centroid incrementally (approximate)
            best_cluster.save(update_fields=["size", "updated_at"])
            logger.debug(
                "Assigned document %s to existing cluster %s (similarity=%.3f)",
                document.id,
                best_cluster.id,
                best_similarity,
            )
            return best_cluster
        else:
            # Create new cluster
            new_cluster = Cluster.objects.create(
                workspace=workspace, centroid=document.embedding, size=1
            )
            ClusterMembership.objects.create(document=document, cluster=new_cluster)
            logger.debug("Created new cluster %s for document %s", new_cluster.id, document.id)
            return new_cluster


def reconcile_cluster_centroids(workspace=None):
    """
    Recompute all cluster centroids from member documents (integrity check).

    Args:
        workspace: Optional workspace to limit reconciliation to
    """
    clusters = Cluster.objects.all()
    if workspace:
        clusters = clusters.filter(workspace=workspace)

    updated_count = 0
    for cluster in clusters:
        new_centroid = compute_cluster_centroid(cluster)
        if new_centroid:
            cluster.centroid = new_centroid
            cluster.size = ClusterMembership.objects.filter(cluster=cluster).count()
            cluster.save(update_fields=["centroid", "size", "updated_at"])
            updated_count += 1
        else:
            # No members, delete empty cluster
            logger.debug("Deleting empty cluster %s", cluster.id)
            cluster.delete()

    logger.info("Reconciled %d cluster centroids", updated_count)
