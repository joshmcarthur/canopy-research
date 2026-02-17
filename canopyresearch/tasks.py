"""
Background tasks for canopyresearch.

Uses Django Tasks (django-tasks-db) for database-backed async execution.
"""

import logging

from django_tasks import task

from canopyresearch.models import Source, Workspace
from canopyresearch.services.ingestion import ingest_source, ingest_workspace

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
    source = Source.objects.select_related("workspace").get(pk=source_id)
    return ingest_source(source)


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
