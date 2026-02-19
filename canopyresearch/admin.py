"""
Django admin configuration for canopyresearch.
"""

from django.contrib import admin
from django.utils.html import format_html

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
from canopyresearch.services.clustering import update_cluster_metrics


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

    list_display = [
        "id",
        "workspace",
        "size",
        "alignment_display",
        "velocity_display",
        "drift_distance_display",
        "metrics_updated_at",
        "created_at",
        "updated_at",
    ]
    list_filter = [
        "workspace",
        "created_at",
        "updated_at",
        "metrics_updated_at",
    ]
    search_fields = ["workspace__name"]
    readonly_fields = ["created_at", "updated_at", "metrics_updated_at"]
    actions = ["recompute_metrics_action"]

    def alignment_display(self, obj):
        """Display alignment with color coding."""
        if obj.alignment is None:
            return format_html('<span style="color: #999;">—</span>')
        color = "#10b981" if obj.alignment >= 0.7 else "#f59e0b" if obj.alignment >= 0.4 else "#999"
        return format_html('<span style="color: {};">{:.2f}</span>', color, obj.alignment)

    alignment_display.short_description = "Alignment"
    alignment_display.admin_order_field = "alignment"

    def velocity_display(self, obj):
        """Display velocity with color coding."""
        if obj.velocity is None:
            return format_html('<span style="color: #999;">—</span>')
        color = "#10b981" if obj.velocity >= 0.5 else "#f59e0b" if obj.velocity >= 0.2 else "#999"
        return format_html('<span style="color: {};">{:.2f}</span>', color, obj.velocity)

    velocity_display.short_description = "Velocity"
    velocity_display.admin_order_field = "velocity"

    def drift_distance_display(self, obj):
        """Display drift distance with color coding."""
        if obj.drift_distance is None:
            return format_html('<span style="color: #999;">—</span>')
        color = "#f59e0b" if obj.drift_distance >= 0.1 else "#999"
        return format_html('<span style="color: {};">{:.3f}</span>', color, obj.drift_distance)

    drift_distance_display.short_description = "Drift"
    drift_distance_display.admin_order_field = "drift_distance"

    @admin.action(description="Recompute metrics for selected clusters")
    def recompute_metrics_action(self, request, queryset):
        """Recompute metrics for selected clusters."""
        updated_count = 0
        for cluster in queryset:
            try:
                update_cluster_metrics(cluster)
                updated_count += 1
            except Exception as e:
                self.message_user(
                    request, f"Error updating cluster {cluster.id}: {str(e)}", level="ERROR"
                )
        self.message_user(
            request,
            f"Successfully updated metrics for {updated_count} cluster(s).",
            level="SUCCESS",
        )


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
