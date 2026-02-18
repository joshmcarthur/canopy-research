"""
Velocity scoring service.

Computes growth velocity metrics for documents and clusters.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from canopyresearch.models import Cluster, ClusterMembership, Document

logger = logging.getLogger(__name__)


def compute_velocity_score(document: Document, days_window: int = 7) -> float:
    """
    Compute velocity score based on recency.

    Uses published_at or ingested_at to determine recency.
    More recent documents get higher scores.

    Args:
        document: Document to score
        days_window: Time window in days for velocity calculation

    Returns:
        Velocity score between 0 and 1 (1.0 = very recent)
    """
    # Use published_at if available, otherwise ingested_at
    timestamp = document.published_at or document.ingested_at
    if not timestamp:
        return 0.0

    now = timezone.now()
    age = now - timestamp

    # If older than window, score is 0
    if age > timedelta(days=days_window):
        return 0.0

    # Score decreases linearly with age
    # Recent (0 days old) = 1.0, old (days_window days old) = 0.0
    days_old = age.total_seconds() / (24 * 3600)
    velocity = 1.0 - (days_old / days_window)
    return max(0.0, float(velocity))


def compute_cluster_velocity_score(cluster: Cluster, days_window: int = 7) -> float:
    """
    Compute velocity score for a cluster based on recent activity.

    Measures growth in cluster size over the time window.

    Args:
        cluster: Cluster to score
        days_window: Time window in days

    Returns:
        Velocity score between 0 and 1
    """
    cutoff = timezone.now() - timedelta(days=days_window)

    # Count recent memberships
    recent_memberships = ClusterMembership.objects.filter(
        cluster=cluster, assigned_at__gte=cutoff
    ).count()

    # Count total memberships
    total_memberships = ClusterMembership.objects.filter(cluster=cluster).count()

    if total_memberships == 0:
        return 0.0

    # Velocity = proportion of members added recently
    velocity = min(1.0, recent_memberships / max(1, total_memberships))
    return float(velocity)
