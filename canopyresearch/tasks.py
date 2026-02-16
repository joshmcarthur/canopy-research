"""
Background tasks for canopyresearch.

These tasks handle periodic operations like fetching documents
from sources and maintaining workspace data.
"""

import logging

from django.utils import timezone

from canopyresearch.models import Document, Workspace
from canopyresearch.services.providers import get_provider_class

logger = logging.getLogger(__name__)


def fetch_workspace_sources(workspace_id: int) -> dict[str, int]:
    """
    Fetch documents from all active sources in a workspace.

    This function:
    1. Loads the workspace and all active (healthy) sources
    2. Resolves the appropriate provider for each source
    3. Fetches normalized documents from each provider
    4. Saves documents to the database (with deduplication)
    5. Updates source status and last_fetched timestamp

    Args:
        workspace_id: The ID of the workspace to fetch sources for

    Returns:
        Dictionary with counts:
        - sources_processed: Number of sources processed
        - documents_fetched: Total documents fetched
        - documents_saved: Total documents saved (after deduplication)
        - errors: Number of sources that encountered errors
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error(f"Workspace {workspace_id} not found")
        return {
            "sources_processed": 0,
            "documents_fetched": 0,
            "documents_saved": 0,
            "errors": 0,
        }

    sources = workspace.sources.filter(status="healthy")
    stats = {
        "sources_processed": 0,
        "documents_fetched": 0,
        "documents_saved": 0,
        "errors": 0,
    }

    for source in sources:
        try:
            # Get provider class and instantiate
            provider_class = get_provider_class(source.provider_type)
            provider = provider_class(source)

            # Fetch documents
            documents_data = provider.fetch_documents()
            stats["documents_fetched"] += len(documents_data)

            # Save documents with deduplication
            saved_count = 0
            for doc_data in documents_data:
                # Normalize published_at if it's a string
                published_at = doc_data.get("published_at")
                if isinstance(published_at, str):
                    # Try to parse common datetime formats
                    # For Phase 1, we'll use timezone.now() as fallback
                    published_at = timezone.now()
                elif published_at is None:
                    published_at = timezone.now()

                # Create or update document
                doc, created = Document.objects.update_or_create(
                    workspace=workspace,
                    source=source,
                    url=doc_data["url"],
                    defaults={
                        "title": doc_data.get("title", ""),
                        "content": doc_data.get("content", ""),
                        "published_at": published_at,
                        "metadata": doc_data.get("metadata", {}),
                    },
                )
                if created:
                    saved_count += 1

            stats["documents_saved"] += saved_count

            # Update source status
            source.last_fetched = timezone.now()
            source.status = "healthy"
            source.save(update_fields=["last_fetched", "status"])

            stats["sources_processed"] += 1
            logger.info(
                f"Processed source {source.name} for workspace {workspace.name}: "
                f"fetched {len(documents_data)}, saved {saved_count}"
            )

        except Exception as e:
            logger.error(f"Error processing source {source.name}: {e}", exc_info=True)
            source.status = "error"
            source.save(update_fields=["status"])
            stats["errors"] += 1

    return stats


def cleanup_old_documents(workspace_id: int, days_old: int = 90) -> int:
    """
    Clean up old documents from a workspace.

    This is an optional maintenance task that removes documents
    older than a specified number of days.

    Args:
        workspace_id: The ID of the workspace to clean up
        days_old: Number of days after which documents are considered old (default: 90)

    Returns:
        Number of documents deleted
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.error(f"Workspace {workspace_id} not found")
        return 0

    cutoff_date = timezone.now() - timezone.timedelta(days=days_old)
    deleted_count, _ = workspace.documents.filter(published_at__lt=cutoff_date).delete()

    logger.info(f"Cleaned up {deleted_count} old documents from workspace {workspace.name}")
    return deleted_count
