"""
Clustering service for canopyresearch.

Handles document-to-cluster assignment and centroid maintenance.
"""

import logging

import numpy as np
from django.db import transaction
from django.utils import timezone

from canopyresearch.models import Cluster, ClusterMembership, Document, Workspace
from canopyresearch.services.scoring import (
    compute_cluster_alignment_score,
    compute_cluster_velocity_score,
)
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

    Uses select_for_update() to prevent race conditions when multiple tasks
    try to create clusters concurrently.

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

    # Assign to best cluster if above threshold, otherwise create new
    # Use select_for_update() to lock the workspace and prevent concurrent cluster creation
    with transaction.atomic():
        # Lock the workspace to prevent concurrent cluster creation
        workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)

        # Find existing clusters in this workspace (inside transaction to see latest state)
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
            # Create new cluster (workspace is locked, so no concurrent creation possible)
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


def track_cluster_drift(cluster: Cluster) -> float | None:
    """
    Track cluster drift by comparing current centroid to previous centroid.

    Args:
        cluster: Cluster to track drift for

    Returns:
        Drift distance (1 - cosine similarity) or None if no previous centroid
    """
    if not cluster.centroid or not isinstance(cluster.centroid, list) or len(cluster.centroid) == 0:
        logger.debug("Cluster %s has no centroid, cannot track drift", cluster.id)
        return None

    if (
        not cluster.previous_centroid
        or not isinstance(cluster.previous_centroid, list)
        or len(cluster.previous_centroid) == 0
    ):
        logger.debug("Cluster %s has no previous centroid, skipping drift tracking", cluster.id)
        return None

    # Compute cosine similarity between current and previous centroid
    similarity = cosine_similarity(cluster.centroid, cluster.previous_centroid)
    # Drift distance = 1 - similarity (higher drift = lower similarity)
    drift_distance = 1.0 - similarity
    return float(drift_distance)


def compute_cluster_metrics(cluster: Cluster) -> dict:
    """
    Compute all metrics for a cluster (alignment, velocity, drift).

    Reuses existing functions: compute_cluster_velocity_score and compute_cluster_alignment_score.
    Ensures centroid is current before computing metrics.

    Args:
        cluster: Cluster to compute metrics for

    Returns:
        Dict with computed metrics: {'alignment': float, 'velocity': float, 'drift_distance': float | None}
    """
    # Ensure centroid is current
    current_centroid = compute_cluster_centroid(cluster)
    if current_centroid:
        # Update centroid if it changed
        if cluster.centroid != current_centroid:
            # Store previous centroid before updating
            if cluster.centroid:
                cluster.previous_centroid = cluster.centroid
            cluster.centroid = current_centroid

    # Compute alignment (reuse existing function)
    alignment = compute_cluster_alignment_score(cluster)

    # Compute velocity (reuse existing function)
    velocity = compute_cluster_velocity_score(cluster)

    # Track drift (compare current to previous centroid)
    drift_distance = track_cluster_drift(cluster)

    metrics = {
        "alignment": alignment,
        "velocity": velocity,
        "drift_distance": drift_distance,
    }

    logger.debug("Computed metrics for cluster %s: %s", cluster.id, metrics)
    return metrics


def update_cluster_metrics(cluster: Cluster) -> dict:
    """
    Compute and update cluster metrics in the database.

    Args:
        cluster: Cluster to update

    Returns:
        Dict with computed metrics
    """
    metrics = compute_cluster_metrics(cluster)

    # Update cluster fields
    cluster.alignment = metrics["alignment"]
    cluster.velocity = metrics["velocity"]
    cluster.drift_distance = metrics["drift_distance"]
    cluster.metrics_updated_at = timezone.now()

    # Save updated fields
    update_fields = ["alignment", "velocity", "drift_distance", "metrics_updated_at", "centroid"]
    if cluster.previous_centroid:
        update_fields.append("previous_centroid")
    cluster.save(update_fields=update_fields)

    logger.info("Updated metrics for cluster %s", cluster.id)
    return metrics


def recompute_cluster_assignments(workspace: Workspace, threshold: float | None = None) -> dict:
    """
    Reassign all documents in a workspace to clusters.

    Reuses existing assign_document_to_cluster function for each document.
    Calls reconcile_cluster_centroids after reassignment.

    Args:
        workspace: Workspace to recompute clusters for
        threshold: Optional threshold override (uses default if None)

    Returns:
        Dict with stats: {'documents_processed': int, 'clusters_created': int, 'clusters_merged': int}
    """
    # Get all documents with embeddings in this workspace
    documents = workspace.documents.exclude(embedding=[]).filter(embedding__isnull=False)

    documents_processed = 0
    clusters_created = set()
    clusters_merged = set()

    # Track initial cluster count
    initial_cluster_ids = set(workspace.clusters.values_list("id", flat=True))

    # Reassign each document
    for document in documents:
        if (
            not document.embedding
            or not isinstance(document.embedding, list)
            or len(document.embedding) == 0
        ):
            continue

        # Remove document from all current clusters
        ClusterMembership.objects.filter(document=document).delete()

        # Assign to best cluster (reuse existing function)
        assigned_threshold = threshold if threshold is not None else DEFAULT_CLUSTER_THRESHOLD
        cluster = assign_document_to_cluster(document, threshold=assigned_threshold)

        if cluster:
            documents_processed += 1
            if cluster.id not in initial_cluster_ids:
                clusters_created.add(cluster.id)
            else:
                clusters_merged.add(cluster.id)

    # Reconcile all cluster centroids (reuse existing function)
    reconcile_cluster_centroids(workspace=workspace)

    stats = {
        "documents_processed": documents_processed,
        "clusters_created": len(clusters_created),
        "clusters_merged": len(clusters_merged),
    }

    logger.info("Recomputed cluster assignments for workspace %s: %s", workspace.id, stats)
    return stats
