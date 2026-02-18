"""
Django models for canopyresearch.
"""

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Workspace(models.Model):
    """Represents a research domain workspace."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="workspaces")
    core_centroid = models.JSONField(default=dict, blank=True)  # Placeholder for future embeddings
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["owner", "-updated_at"]),
        ]

    def __str__(self):
        return self.name


class Source(models.Model):
    """Represents a content source for a workspace."""

    PROVIDER_CHOICES = [
        ("rss", "RSS Feed"),
        ("hackernews", "Hacker News"),
        ("subreddit", "Subreddit"),
    ]

    STATUS_CHOICES = [
        ("healthy", "Healthy"),
        ("error", "Error"),
        ("paused", "Paused"),
    ]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="sources")
    name = models.CharField(max_length=200)
    provider_type = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    config = models.JSONField(default=dict)  # Provider-specific configuration
    last_fetched = models.DateTimeField(null=True, blank=True)
    last_successful_fetch = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    consecutive_failures = models.IntegerField(default=0)
    auto_pause_threshold = models.IntegerField(default=5)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="healthy")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [["workspace", "name"]]
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["workspace", "-last_fetched"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_provider_type_display()})"


class Document(models.Model):
    """
    Represents a normalized document at the workspace level.

    Documents are deduplicated by content_hash within a workspace, allowing the same
    document (same URL/title/content) to be associated with multiple sources without
    creating duplicate document records.
    """

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="documents")
    sources = models.ManyToManyField(Source, through="DocumentSource", related_name="documents")
    external_id = models.CharField(
        max_length=255, blank=True
    )  # Provider-specific ID (HN, Reddit, GUID)
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=2000)
    content = models.TextField()
    published_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # Optional fields like author, tags
    embedding = models.JSONField(default=list, blank=True)  # Placeholder for future embeddings
    content_hash = models.CharField(
        max_length=64, db_index=True, blank=True
    )  # Deduplication (SHA-256)
    ingested_at = models.DateTimeField(null=True, blank=True)
    raw_payload = models.JSONField(null=True, blank=True)  # Optional debugging/traceability
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["workspace", "-published_at"]),
            models.Index(fields=["workspace", "content_hash"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "content_hash"],
                condition=models.Q(content_hash__gt=""),
                name="unique_doc_content_hash_per_workspace",
            ),
        ]

    def __str__(self):
        return self.title


class DocumentSource(models.Model):
    """
    Join model representing the association between a Document and a Source.

    This allows tracking which sources a document came from, and when it was
    first discovered from each source. The same document can be associated
    with multiple sources if it appears in multiple feeds.
    """

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="document_sources"
    )
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="document_sources")
    discovered_at = models.DateTimeField(
        auto_now_add=True
    )  # When this document was first found from this source

    class Meta:
        unique_together = [["document", "source"]]
        indexes = [
            models.Index(fields=["source", "-discovered_at"]),
        ]

    def __str__(self):
        return f"{self.document.title} from {self.source.name}"


class IngestionLog(models.Model):
    """Tracks ingestion events per source for observability."""

    STATUS_CHOICES = [
        ("success", "Success"),
        ("error", "Error"),
    ]

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="ingestion_logs")
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    documents_found = models.IntegerField(default=0)
    documents_created = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["source", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.source.name} ingestion at {self.started_at}"
