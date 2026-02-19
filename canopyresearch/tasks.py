"""
Background tasks for canopyresearch.

Uses Django Tasks (django-tasks-db) for database-backed async execution.
"""

import logging

from django_tasks import task

from canopyresearch.models import Cluster, Document, Source, Workspace
from canopyresearch.services.clustering import (
    assign_document_to_cluster,
    recompute_cluster_assignments,
    reconcile_cluster_centroids,
    update_cluster_metrics,
)
from canopyresearch.services.core import seed_workspace_core, update_workspace_core_centroid
from canopyresearch.services.embeddings import get_embedding_backend
from canopyresearch.services.extraction import extract_and_clean_content
from canopyresearch.services.ingestion import ingest_source, ingest_workspace
from canopyresearch.services.scoring import (
    compute_alignment_score,
    compute_novelty_score,
    compute_velocity_score,
)

logger = logging.getLogger(__name__)


@task
def task_ingest_workspace(workspace_id: int) -> dict[str, int]:
    """Ingest documents from all healthy sources in a workspace."""
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error("Workspace %s not found", workspace_id)
        return {"sources_processed": 0, "documents_fetched": 0, "documents_saved": 0, "errors": 0}
    return ingest_workspace(workspace)


@task
def task_ingest_source(source_id: int) -> tuple[int, int]:
    """Ingest documents from a single source."""
    try:
        source = Source.objects.select_related("workspace").get(pk=source_id)
    except Source.DoesNotExist:
        logger.error("Source %s not found", source_id)
        return (0, 0)
    return ingest_source(source)


@task
def task_extract_and_embed_document(document_id: int) -> dict:
    """
    Extract clean content and compute embedding for a document.

    Returns dict with status and embedding metadata.
    """
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("Document %s not found", document_id)
        return {"status": "error", "message": "Document not found"}

    try:
        # Extract and clean content
        cleaned_content = extract_and_clean_content(document.content, document.url)

        # Update document content if cleaned version is better
        if cleaned_content and len(cleaned_content) > len(document.content):
            document.content = cleaned_content
            document.save(update_fields=["content", "updated_at"])

        # Compute embedding
        backend = get_embedding_backend()
        embeddings = backend.embed_texts([cleaned_content or document.content])

        if not embeddings or not embeddings[0]:
            logger.warning("Failed to generate embedding for document %s", document_id)
            return {"status": "error", "message": "Failed to generate embedding"}

        # Store embedding and metadata
        document.embedding = embeddings[0]
        if not document.metadata:
            document.metadata = {}
        document.metadata["embedding_model"] = backend.model_name
        document.metadata["embedding_dim"] = backend.embedding_dim
        document.save(update_fields=["embedding", "metadata", "updated_at"])

        logger.info("Computed embedding for document %s", document_id)
        return {
            "status": "success",
            "embedding_dim": backend.embedding_dim,
            "model": backend.model_name,
        }
    except Exception as e:
        logger.exception("Failed to extract/embed document %s: %s", document_id, e)
        return {"status": "error", "message": str(e)}


@task
def task_assign_cluster(document_id: int) -> dict:
    """Assign a document to a cluster."""
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("Document %s not found", document_id)
        return {"status": "error", "message": "Document not found"}

    try:
        cluster = assign_document_to_cluster(document)
        if cluster:
            return {"status": "success", "cluster_id": cluster.id}
        else:
            return {"status": "skipped", "message": "Document has no embedding"}
    except Exception as e:
        logger.exception("Failed to assign cluster for document %s: %s", document_id, e)
        return {"status": "error", "message": str(e)}


@task
def task_score_document(document_id: int) -> dict:
    """Compute all scores for a document."""
    try:
        document = Document.objects.select_related("workspace").get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("Document %s not found", document_id)
        return {"status": "error", "message": "Document not found"}

    try:
        scores = {
            "alignment": compute_alignment_score(document),
            "novelty": compute_novelty_score(document),
            "velocity": compute_velocity_score(document),
        }

        # Store scores in metadata
        if not document.metadata:
            document.metadata = {}
        document.metadata["scores"] = scores
        document.save(update_fields=["metadata", "updated_at"])

        logger.debug("Computed scores for document %s: %s", document_id, scores)
        return {"status": "success", "scores": scores}
    except Exception as e:
        logger.exception("Failed to score document %s: %s", document_id, e)
        return {"status": "error", "message": str(e)}


@task
def task_update_workspace_core(workspace_id: int) -> dict:
    """Update workspace core centroid (seed if needed, then update from feedback)."""
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error("Workspace %s not found", workspace_id)
        return {"status": "error", "message": "Workspace not found"}

    try:
        # Seed if no core exists
        if not workspace.core_centroid or not workspace.core_centroid.get("vector"):
            logger.info("Seeding workspace %s core", workspace_id)
            seed_workspace_core(workspace)

        # Update centroid from feedback
        centroid = update_workspace_core_centroid(workspace)
        if centroid:
            return {"status": "success", "centroid_dim": len(centroid)}
        else:
            return {"status": "warning", "message": "No valid documents for centroid"}
    except Exception as e:
        logger.exception("Failed to update workspace core %s: %s", workspace_id, e)
        return {"status": "error", "message": str(e)}


@task
def task_process_document(document_id: int) -> dict:
    """
    Full processing pipeline for a document: extract → embed → cluster → score.

    This is the main entry point for processing newly ingested documents.
    """
    try:
        Document.objects.select_related("workspace").get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("Document %s not found", document_id)
        return {"status": "error", "message": "Document not found"}

    results = {}

    # Step 1: Extract and embed
    embed_result_obj = task_extract_and_embed_document.enqueue(document_id=document_id)
    embed_result = embed_result_obj.return_value
    results["embedding"] = embed_result
    if embed_result.get("status") != "success":
        return {"status": "error", "step": "embedding", "results": results}

    # Step 2: Assign to cluster
    cluster_result_obj = task_assign_cluster.enqueue(document_id=document_id)
    cluster_result = cluster_result_obj.return_value
    results["clustering"] = cluster_result

    # Step 3: Score
    score_result_obj = task_score_document.enqueue(document_id=document_id)
    score_result = score_result_obj.return_value
    results["scoring"] = score_result

    logger.info("Processed document %s: %s", document_id, results)
    return {"status": "success", "results": results}


@task
def task_process_workspace(workspace_id: int) -> dict:
    """
    Batch process all documents in a workspace (backfill embeddings/scores).

    Processes documents that don't have embeddings yet.
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error("Workspace %s not found", workspace_id)
        return {"status": "error", "message": "Workspace not found"}

    # Find documents without embeddings
    documents = workspace.documents.filter(embedding=[])
    total = documents.count()

    processed = 0
    errors = 0

    for doc in documents:
        try:
            result = task_process_document.enqueue(document_id=doc.id).return_value
            if result.get("status") == "success":
                processed += 1
            else:
                errors += 1
        except Exception as e:
            logger.exception("Error processing document %s: %s", doc.id, e)
            errors += 1

    logger.info(
        "Processed workspace %s: %d/%d documents processed, %d errors",
        workspace_id,
        processed,
        total,
        errors,
    )
    return {"status": "success", "processed": processed, "total": total, "errors": errors}


@task
def task_reconcile_clusters(workspace_id: int = None) -> dict:
    """
    Reconcile cluster centroids (recompute from members).

    Args:
        workspace_id: Optional workspace ID to limit reconciliation
    """
    try:
        workspace = None
        if workspace_id:
            workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error("Workspace %s not found", workspace_id)
        return {"status": "error", "message": "Workspace not found"}

    try:
        reconcile_cluster_centroids(workspace=workspace)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Failed to reconcile clusters: %s", e)
        return {"status": "error", "message": str(e)}


@task
def task_update_cluster_metrics(workspace_id: int = None, cluster_id: int = None) -> dict:
    """
    Update metrics for clusters (alignment, velocity, drift).

    Args:
        workspace_id: Optional workspace ID to limit updates
        cluster_id: Optional cluster ID to update single cluster
    """
    try:
        if cluster_id:
            clusters = Cluster.objects.filter(pk=cluster_id)
        elif workspace_id:
            clusters = Cluster.objects.filter(workspace_id=workspace_id)
        else:
            clusters = Cluster.objects.all()
    except Cluster.DoesNotExist:
        logger.error("Cluster %s not found", cluster_id)
        return {"status": "error", "message": "Cluster not found"}

    updated_count = 0
    errors = 0

    for cluster in clusters:
        try:
            update_cluster_metrics(cluster)
            updated_count += 1
        except Exception as e:
            logger.exception("Failed to update metrics for cluster %s: %s", cluster.id, e)
            errors += 1

    logger.info("Updated metrics for %d clusters (%d errors)", updated_count, errors)
    return {
        "status": "success",
        "updated": updated_count,
        "errors": errors,
    }


@task
def task_recompute_clusters(workspace_id: int, threshold: float = None) -> dict:
    """
    Periodic task to recompute cluster assignments.

    Reassigns all documents to clusters and reconciles centroids.

    Args:
        workspace_id: Workspace ID to recompute clusters for
        threshold: Optional threshold override for reassignment
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error("Workspace %s not found", workspace_id)
        return {"status": "error", "message": "Workspace not found"}

    try:
        # Reassign all documents to clusters
        stats = recompute_cluster_assignments(workspace, threshold=threshold)

        # Reconcile centroids (reuse existing function)
        reconcile_cluster_centroids(workspace=workspace)

        logger.info("Recomputed clusters for workspace %s: %s", workspace_id, stats)
        return {"status": "success", **stats}
    except Exception as e:
        logger.exception("Failed to recompute clusters for workspace %s: %s", workspace_id, e)
        return {"status": "error", "message": str(e)}


def cleanup_old_documents(workspace_id: int, days_old: int = 90) -> int:
    """
    Clean up old documents from a workspace.

    Optional maintenance task. Not decorated as @task—call directly or enqueue if needed.
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error("Workspace %s not found", workspace_id)
        return 0

    from django.utils import timezone

    cutoff_date = timezone.now() - timezone.timedelta(days=days_old)
    deleted_count, _ = workspace.documents.filter(published_at__lt=cutoff_date).delete()
    logger.info("Cleaned up %d old documents from workspace %s", deleted_count, workspace.name)
    return deleted_count
