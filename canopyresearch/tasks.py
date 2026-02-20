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
    compute_relevance_score,
    compute_velocity_score,
)

logger = logging.getLogger(__name__)


# Helper functions (not tasks) that can be called directly
def _extract_and_embed_document(document_id: int) -> dict:
    """
    Extract clean content and compute embedding for a document.

    Helper function that can be called directly (not a task).
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


def _assign_cluster(document_id: int) -> dict:
    """
    Assign a document to a cluster.

    Helper function that can be called directly (not a task).
    """
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


def _score_document(document_id: int) -> dict:
    """
    Compute all scores for a document and store in first-class fields.

    Helper function that can be called directly (not a task).
    """
    from django.utils import timezone

    try:
        document = (
            Document.objects.select_related("workspace")
            .prefetch_related("sources", "cluster_memberships")
            .get(pk=document_id)
        )
    except Document.DoesNotExist:
        logger.error("Document %s not found", document_id)
        return {"status": "error", "message": "Document not found"}

    try:
        # Compute component scores
        alignment = compute_alignment_score(document)
        velocity = compute_velocity_score(document)
        novelty = compute_novelty_score(document)

        # Store component scores in first-class fields
        document.alignment = alignment
        document.velocity = velocity
        document.novelty = novelty

        # Compute combined relevance score
        relevance = compute_relevance_score(document)

        # Store relevance and timestamp
        document.relevance = relevance
        document.scored_at = timezone.now()

        # Save all score fields
        document.save(
            update_fields=[
                "alignment",
                "velocity",
                "novelty",
                "relevance",
                "scored_at",
                "updated_at",
            ]
        )

        scores = {
            "alignment": alignment,
            "velocity": velocity,
            "novelty": novelty,
            "relevance": relevance,
        }

        logger.debug("Computed scores for document %s: %s", document_id, scores)
        return {"status": "success", "scores": scores}
    except Exception as e:
        logger.exception("Failed to score document %s: %s", document_id, e)
        return {"status": "error", "message": str(e)}


def _process_document_sync(document_id: int) -> dict:
    """
    Synchronous version of document processing pipeline.

    Helper function that can be called directly (not a task).
    Used internally by task_process_workspace.
    """
    try:
        Document.objects.select_related("workspace").get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("Document %s not found", document_id)
        return {"status": "error", "message": "Document not found"}

    results = {}

    # Step 1: Extract and embed
    embed_result = _extract_and_embed_document(document_id=document_id)
    results["embedding"] = embed_result
    if embed_result.get("status") != "success":
        return {"status": "error", "step": "embedding", "results": results}

    # Step 2: Assign to cluster
    cluster_result = _assign_cluster(document_id=document_id)
    results["clustering"] = cluster_result

    # Step 3: Score
    score_result = _score_document(document_id=document_id)
    results["scoring"] = score_result

    logger.info("Processed document %s: %s", document_id, results)
    return {"status": "success", "results": results}


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
    return _extract_and_embed_document(document_id)


@task
def task_assign_cluster(document_id: int) -> dict:
    """Assign a document to a cluster."""
    return _assign_cluster(document_id)


@task
def task_score_document(document_id: int) -> dict:
    """Compute all scores for a document."""
    return _score_document(document_id)


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
            # Trigger rescore of workspace documents (alignment depends on core)
            task_rescore_workspace.enqueue(workspace_id=workspace_id)
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
    return _process_document_sync(document_id=document_id)


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
            # Call the helper function directly for synchronous execution
            # We can't call task_process_document directly since it's a Task object
            # Instead, we'll call the underlying logic
            result = _process_document_sync(document_id=doc.id)
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

        # Trigger novelty recompute (novelty depends on cluster assignments)
        task_recompute_novelty.enqueue(workspace_id=workspace_id)

        logger.info("Recomputed clusters for workspace %s: %s", workspace_id, stats)
        return {"status": "success", **stats}
    except Exception as e:
        logger.exception("Failed to recompute clusters for workspace %s: %s", workspace_id, e)
        return {"status": "error", "message": str(e)}


@task
def task_rescore_workspace(workspace_id: int, scope: str = "all") -> dict:
    """
    Rescore all documents in a workspace (recompute alignment, velocity, novelty, relevance).

    This should be called after workspace core centroid updates, since alignment depends on core.

    Args:
        workspace_id: Workspace ID to rescore
        scope: 'all' to rescore all documents, 'recent' to only rescore documents updated recently
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error("Workspace %s not found", workspace_id)
        return {"status": "error", "message": "Workspace not found"}

    # Get documents with embeddings
    documents = workspace.documents.exclude(embedding=[]).filter(embedding__isnull=False)
    if scope == "recent":
        from datetime import timedelta

        from django.utils import timezone

        cutoff = timezone.now() - timedelta(days=7)
        documents = documents.filter(updated_at__gte=cutoff)

    total = documents.count()
    rescored = 0
    errors = 0

    for doc in documents:
        try:
            result = _score_document(document_id=doc.id)
            if result.get("status") == "success":
                rescored += 1
            else:
                errors += 1
        except Exception as e:
            logger.exception("Error rescoring document %s: %s", doc.id, e)
            errors += 1

    logger.info(
        "Rescored workspace %s: %d/%d documents rescored, %d errors",
        workspace_id,
        rescored,
        total,
        errors,
    )
    return {"status": "success", "rescored": rescored, "total": total, "errors": errors}


@task
def task_recompute_novelty(workspace_id: int) -> dict:
    """
    Recompute novelty scores for all documents in a workspace.

    This should be called after cluster recomputation, since novelty depends on cluster assignments.

    Args:
        workspace_id: Workspace ID to recompute novelty for
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error("Workspace %s not found", workspace_id)
        return {"status": "error", "message": "Workspace not found"}

    from django.utils import timezone

    # Get documents with embeddings
    documents = (
        workspace.documents.exclude(embedding=[])
        .filter(embedding__isnull=False)
        .prefetch_related("cluster_memberships")
    )

    total = documents.count()
    recomputed = 0
    errors = 0

    for doc in documents:
        try:
            novelty = compute_novelty_score(doc)
            doc.novelty = novelty
            doc.scored_at = timezone.now()
            doc.save(update_fields=["novelty", "scored_at", "updated_at"])

            # Also recompute relevance since novelty changed
            relevance = compute_relevance_score(doc)
            doc.relevance = relevance
            doc.save(update_fields=["relevance", "updated_at"])

            recomputed += 1
        except Exception as e:
            logger.exception("Error recomputing novelty for document %s: %s", doc.id, e)
            errors += 1

    logger.info(
        "Recomputed novelty for workspace %s: %d/%d documents, %d errors",
        workspace_id,
        recomputed,
        total,
        errors,
    )
    return {"status": "success", "recomputed": recomputed, "total": total, "errors": errors}


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
