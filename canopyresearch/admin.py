"""
Django admin configuration for canopyresearch.
"""

from django.contrib import admin

from canopyresearch.models import (
    Cluster,
    ClusterMembership,
    Document,
    IngestionLog,
    Source,
    Workspace,
    WorkspaceCoreFeedback,
    WorkspaceCoreSeed,
)


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    """Admin interface for Workspace model."""

    list_display = ["name", "owner", "created_at", "updated_at"]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    """Admin interface for Source model."""

    list_display = [
        "name",
        "workspace",
        "provider_type",
        "status",
        "last_successful_fetch",
        "last_fetched",
    ]
    list_filter = ["provider_type", "status", "last_fetched"]
    search_fields = ["name", "workspace__name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Admin interface for Document model."""

    list_display = ["title", "workspace", "sources_display", "published_at", "created_at"]
    list_filter = ["published_at", "created_at", "workspace", "sources"]
    search_fields = ["title", "url", "content"]
    readonly_fields = ["content_hash", "created_at", "updated_at"]

    def sources_display(self, obj):
        """Display sources as comma-separated list."""
        return ", ".join([source.name for source in obj.sources.all()])

    sources_display.short_description = "Sources"


@admin.register(IngestionLog)
class IngestionLogAdmin(admin.ModelAdmin):
    """Admin interface for IngestionLog model."""

    list_display = [
        "source",
        "started_at",
        "finished_at",
        "documents_found",
        "documents_created",
        "status",
    ]
    list_filter = ["status", "started_at"]
    search_fields = ["source__name", "error_message"]
    readonly_fields = [
        "source",
        "started_at",
        "finished_at",
        "documents_found",
        "documents_created",
        "status",
        "error_message",
    ]


@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    """Admin interface for Cluster model."""

    list_display = ["id", "workspace", "size", "created_at", "updated_at"]
    list_filter = ["workspace", "created_at", "updated_at"]
    search_fields = ["workspace__name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ClusterMembership)
class ClusterMembershipAdmin(admin.ModelAdmin):
    """Admin interface for ClusterMembership model."""

    list_display = ["document", "cluster", "assigned_at"]
    list_filter = ["assigned_at", "cluster__workspace"]
    search_fields = ["document__title", "cluster__workspace__name"]
    readonly_fields = ["assigned_at"]


@admin.register(WorkspaceCoreSeed)
class WorkspaceCoreSeedAdmin(admin.ModelAdmin):
    """Admin interface for WorkspaceCoreSeed model."""

    list_display = ["workspace", "document", "seed_source", "created_at"]
    list_filter = ["seed_source", "created_at", "workspace"]
    search_fields = ["workspace__name", "document__title"]
    readonly_fields = ["created_at"]


@admin.register(WorkspaceCoreFeedback)
class WorkspaceCoreFeedbackAdmin(admin.ModelAdmin):
    """Admin interface for WorkspaceCoreFeedback model."""

    list_display = ["workspace", "document", "vote", "user", "created_at"]
    list_filter = ["vote", "created_at", "workspace"]
    search_fields = ["workspace__name", "document__title", "user__username"]
    readonly_fields = ["created_at"]
