"""
Ingestion service layer for canopyresearch.

Handles document normalization, deduplication, persistence, and error resilience.
"""

import hashlib
import logging

from django.utils import timezone

from canopyresearch.models import Document, DocumentSource, IngestionLog, Source
from canopyresearch.services.providers import get_provider_class

logger = logging.getLogger(__name__)


def compute_hash(data: dict) -> str:
    """
    Deterministic hash for deduplication.

    Uses: title (stripped, lowercased) + url + content[:500]
    """
    title = (data.get("title") or "").strip().lower()
    url = data.get("url") or ""
    content = (data.get("content") or "")[:500]
    return hashlib.sha256(f"{title}{url}{content}".encode()).hexdigest()


def persist_document(workspace, source: Source, data: dict) -> bool:
    """
    Persist a normalized document, deduplicating by content_hash.

    Returns True if a new document was created, False if deduplicated.
    When deduplicating, still creates DocumentSource link if not present.
    """
    content_hash = compute_hash(data)
    existing = Document.objects.filter(workspace=workspace, content_hash=content_hash).first()
    if existing:
        DocumentSource.objects.get_or_create(document=existing, source=source)
        return False

    published_at = data.get("published_at")
    if published_at is None:
        published_at = timezone.now()

    doc = Document.objects.create(
        workspace=workspace,
        external_id=data.get("external_id") or "",
        title=data.get("title", ""),
        url=data.get("url", ""),
        content=data.get("content", ""),
        published_at=published_at,
        metadata=data.get("metadata", {}),
        content_hash=content_hash,
        ingested_at=timezone.now(),
    )
    DocumentSource.objects.get_or_create(document=doc, source=source)
    return True


def mark_source_error(source: Source, error: Exception) -> None:
    """Record error on source and optionally pause if threshold exceeded."""
    source.last_error = str(error)
    source.consecutive_failures += 1
    if source.consecutive_failures >= source.auto_pause_threshold:
        source.status = "paused"
    else:
        source.status = "error"
    source.save(update_fields=["last_error", "consecutive_failures", "status", "updated_at"])


def ingest_source(source: Source) -> tuple[int, int]:
    """
    Ingest documents from a single source.

    Returns (documents_found, documents_created).
    """
    started_at = timezone.now()
    workspace = source.workspace
    log = IngestionLog.objects.create(
        source=source,
        started_at=started_at,
        documents_found=0,
        documents_created=0,
        status="success",
    )

    try:
        provider_class = get_provider_class(source.provider_type)
        provider = provider_class(source)
        raw_docs = provider.fetch()
        documents_found = len(raw_docs)
        log.documents_found = documents_found
        log.save(update_fields=["documents_found"])

        documents_created = 0
        for raw in raw_docs:
            normalized = provider.normalize(raw)
            if persist_document(workspace, source, normalized):
                documents_created += 1

        log.documents_created = documents_created
        log.finished_at = timezone.now()
        log.save(update_fields=["documents_created", "finished_at"])

        source.last_successful_fetch = timezone.now()
        source.last_fetched = timezone.now()
        source.consecutive_failures = 0
        source.status = "healthy"
        source.save(
            update_fields=[
                "last_successful_fetch",
                "last_fetched",
                "consecutive_failures",
                "status",
                "updated_at",
            ]
        )

        logger.info(
            "Ingested source %s: found=%d created=%d",
            source.name,
            documents_found,
            documents_created,
        )
        return documents_found, documents_created

    except Exception as e:
        mark_source_error(source, e)
        log.finished_at = timezone.now()
        log.status = "error"
        log.error_message = str(e)
        log.save(update_fields=["finished_at", "status", "error_message"])
        logger.exception("Ingestion failed for source %s: %s", source.name, e)
        raise


def ingest_workspace(workspace) -> dict[str, int]:
    """
    Ingest documents from all healthy sources in a workspace.

    Returns dict with sources_processed, documents_fetched, documents_saved, errors.
    """
    sources = workspace.sources.filter(status="healthy")
    stats = {"sources_processed": 0, "documents_fetched": 0, "documents_saved": 0, "errors": 0}

    for source in sources:
        try:
            found, created = ingest_source(source)
            stats["documents_fetched"] += found
            stats["documents_saved"] += created
            stats["sources_processed"] += 1
        except Exception:
            stats["errors"] += 1

    return stats
