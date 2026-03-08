"""
Django views for canopyresearch.
"""

import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from canopyresearch.forms import SourceForm, WorkspaceForm
from canopyresearch.models import Cluster, Document, IngestionLog, Source, Workspace, WorkspaceCoreFeedback
from canopyresearch.services.core import add_core_feedback, seed_workspace_core
from canopyresearch.services.source_discovery import (
    auto_discover_and_create_sources,
    create_source_from_candidate,
    discover_source_candidates,
    extract_search_terms,
    initialize_workspace_search_terms,
    update_search_terms_from_feedback,
)
from canopyresearch.tasks import (
    task_ingest_workspace,
    task_reembed_workspace,
    task_update_workspace_core,
)

logger = logging.getLogger(__name__)


@login_required
def workspace_detail(request, workspace_id):
    """Redirect to workspace sources tab."""
    get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    return redirect("source_list", workspace_id=workspace_id)


@login_required
def workspace_switch(request, workspace_id):
    """
    HTMX endpoint for switching active workspace.

    Returns a partial HTML response with workspace context.
    """
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    sources = workspace.sources.all()
    documents = workspace.documents.prefetch_related("sources").order_by("-published_at")[:20]

    context = {
        "workspace": workspace,
        "sources": sources,
        "documents": documents,
    }
    return render(request, "canopyresearch/workspace_content.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def workspace_create(request):
    """Create a new workspace."""
    if request.method == "POST":
        form = WorkspaceForm(request.POST)
        if form.is_valid():
            workspace = form.save(commit=False)
            workspace.owner = request.user
            workspace.save()
            # Extract initial search terms
            initialize_workspace_search_terms(workspace)
            # Automatically discover and create sources
            try:
                source_counts = auto_discover_and_create_sources(
                    workspace, max_sources_per_provider=3
                )
                if source_counts.get("total", 0) > 0:
                    # Trigger background ingestion to populate workspace with content
                    task_ingest_workspace.enqueue(workspace_id=workspace.id)
                    messages.success(
                        request,
                        f'Workspace "{workspace.name}" created with {source_counts["total"]} sources discovered automatically. Content ingestion has started.',
                    )
                else:
                    messages.success(
                        request,
                        f'Workspace "{workspace.name}" created successfully. No sources were automatically discovered.',
                    )
            except Exception as e:
                logger.exception(
                    "Failed to auto-discover sources for workspace %s: %s", workspace.id, e
                )
                messages.success(
                    request,
                    f'Workspace "{workspace.name}" created successfully. Source discovery encountered an error.',
                )
            return redirect("workspace_detail", workspace_id=workspace.id)
    else:
        form = WorkspaceForm()

    context = {"form": form}
    return render(request, "canopyresearch/workspace_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def workspace_edit(request, workspace_id):
    """Edit an existing workspace. Returns modal partial for HTMX GET, redirect/swap for POST."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)

    if request.method == "POST":
        form = WorkspaceForm(request.POST, instance=workspace)
        if form.is_valid():
            form.save()
            # Update search terms if name/description changed
            initialize_workspace_search_terms(workspace)
            messages.success(request, f'Workspace "{workspace.name}" updated successfully.')
            if request.headers.get("HX-Request"):
                # HTMX request - close dialog and refresh page
                response = HttpResponse(
                    "<script>"
                    'document.body.dispatchEvent(new CustomEvent("closeDialog"));'
                    "window.location.reload();"
                    "</script>"
                )
                return response
            return redirect("workspace_detail", workspace_id=workspace.id)
        if request.headers.get("HX-Request"):
            # Form has errors, re-render modal form
            context = {"workspace": workspace, "form": form}
            return render(request, "canopyresearch/partials/workspace_edit_form.html", context)
    else:
        form = WorkspaceForm(instance=workspace)

    context = {
        "workspace": workspace,
        "form": form,
    }
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/workspace_edit_form.html", context)
    return redirect("workspace_detail", workspace_id=workspace.id)


@login_required
@require_http_methods(["GET", "POST"])
def workspace_delete(request, workspace_id):
    """Delete a workspace. GET returns confirm dialog partial, POST performs delete."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)

    if request.method == "POST":
        workspace_name = workspace.name
        workspace.delete()  # CASCADE will delete all sources, documents, clusters, etc.
        messages.success(request, f'Workspace "{workspace_name}" deleted successfully.')
        return redirect("workspace_create")

    context = {"workspace": workspace}
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/workspace_delete_confirm.html", context)
    return redirect("workspace_detail", workspace_id=workspace.id)


@login_required
def source_list(request, workspace_id):
    """List sources for a workspace. Returns partial for HTMX, full shell otherwise."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    sources = workspace.sources.all()

    context = {
        "workspace": workspace,
        "sources": sources,
    }
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/sources_panel.html", context)
    context["tab_content_template"] = "canopyresearch/partials/sources_panel.html"
    context["active_tab"] = "sources"
    return render(request, "canopyresearch/workspace_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def source_create(request, workspace_id):
    """Create a new source for a workspace."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)

    if request.method == "POST":
        form = SourceForm(request.POST, workspace=workspace)
        if form.is_valid():
            source = form.save(commit=False)
            source.workspace = workspace
            source.save()
            messages.success(request, f'Source "{source.name}" created successfully.')
            if request.headers.get("HX-Request"):
                # HTMX request - refresh sources panel and close dialog
                sources_url = reverse("source_list", args=[workspace.id])
                response = HttpResponse(
                    f'<div hx-get="{sources_url}" '
                    'hx-trigger="load" hx-swap="innerHTML" hx-target="#tab-content">Loading...</div>'
                )
                response["HX-Retarget"] = "#tab-content"
                response["HX-Reswap"] = "innerHTML"
                response["HX-Trigger"] = json.dumps({"closeDialog": True})
                return response
            return redirect("source_list", workspace_id=workspace.id)
        if request.headers.get("HX-Request"):
            # Form has errors, re-render modal form
            context = {"workspace": workspace, "form": form}
            return render(request, "canopyresearch/partials/source_create_form.html", context)
        # Non-HTMX POST with invalid form - re-render full-page form with errors
        context = {"workspace": workspace, "form": form}
        return render(request, "canopyresearch/source_form.html", context)
    else:
        form = SourceForm(workspace=workspace)

    context = {
        "workspace": workspace,
        "form": form,
    }
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/source_create_form.html", context)
    return render(request, "canopyresearch/source_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def source_edit(request, workspace_id, source_id):
    """Edit an existing source. Returns modal partial for HTMX GET, redirect/swap for POST."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    source = get_object_or_404(Source, pk=source_id, workspace=workspace)

    if request.method == "POST":
        form = SourceForm(request.POST, instance=source, workspace=workspace)
        if form.is_valid():
            form.save()
            messages.success(request, f'Source "{source.name}" updated successfully.')
            if request.headers.get("HX-Request"):
                sources_url = reverse("source_list", args=[workspace.id])
                response = HttpResponse(
                    f'<div hx-get="{sources_url}" '
                    'hx-trigger="load" hx-swap="innerHTML" hx-target="#tab-content">Loading...</div>'
                )
                response["HX-Retarget"] = "#tab-content"
                response["HX-Reswap"] = "innerHTML"
                response["HX-Trigger"] = json.dumps({"closeDialog": True})
                return response
            return redirect("source_list", workspace_id=workspace.id)
        if request.headers.get("HX-Request"):
            context = {"workspace": workspace, "source": source, "form": form}
            return render(request, "canopyresearch/partials/source_edit_form.html", context)
    else:
        form = SourceForm(instance=source, workspace=workspace)

    context = {
        "workspace": workspace,
        "source": source,
        "form": form,
    }
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/source_edit_form.html", context)
    return render(request, "canopyresearch/source_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def source_delete(request, workspace_id, source_id):
    """Delete a source. GET returns confirm dialog partial, POST performs delete."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    source = get_object_or_404(Source, pk=source_id, workspace=workspace)

    if request.method == "POST":
        source_name = source.name
        source.delete()
        messages.success(request, f'Source "{source_name}" deleted successfully.')
        if request.headers.get("HX-Request"):
            sources_url = reverse("source_list", args=[workspace.id])
            response = HttpResponse(
                f'<div hx-get="{sources_url}" '
                'hx-trigger="load" hx-swap="innerHTML" hx-target="#tab-content">Loading...</div>'
            )
            response["HX-Retarget"] = "#tab-content"
            response["HX-Reswap"] = "innerHTML"
            response["HX-Trigger"] = json.dumps({"closeDialog": True})
            return response
        return redirect("source_list", workspace_id=workspace.id)

    context = {"workspace": workspace, "source": source}
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/source_delete_confirm.html", context)
    return redirect("source_list", workspace_id=workspace.id)


@login_required
@require_http_methods(["GET", "POST"])
def source_discover(request, workspace_id):
    """Discover source candidates for a workspace."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)

    if request.method == "POST":
        # Create sources from selected candidates
        candidate_ids = request.POST.getlist("candidate_ids")
        provider_type = request.POST.get("provider_type")

        if not candidate_ids or not provider_type:
            messages.error(request, "Please select at least one source candidate.")
            return redirect("source_discover", workspace_id=workspace.id)

        # Get candidates for this provider type
        all_candidates = discover_source_candidates(workspace, provider_type)
        created_count = 0

        for candidate_id in candidate_ids:
            try:
                idx = int(candidate_id)
                if 0 <= idx < len(all_candidates):
                    candidate = all_candidates[idx]
                    create_source_from_candidate(workspace, candidate)
                    created_count += 1
            except (ValueError, IndexError):
                continue

        if created_count > 0:
            messages.success(request, f"Created {created_count} source(s) successfully.")
        else:
            messages.error(request, "Failed to create sources. Please try again.")

        if request.headers.get("HX-Request"):
            sources_url = reverse("source_list", args=[workspace.id])
            response = HttpResponse(
                f'<div hx-get="{sources_url}" '
                'hx-trigger="load" hx-swap="innerHTML" hx-target="#tab-content">Loading...</div>'
            )
            response["HX-Retarget"] = "#tab-content"
            response["HX-Reswap"] = "innerHTML"
            return response

        return redirect("source_list", workspace_id=workspace.id)

    # GET: Show discovery interface
    terms = extract_search_terms(workspace)
    candidates_by_provider = {}

    for provider_type in ["hackernews", "subreddit", "rss"]:
        try:
            candidates = discover_source_candidates(workspace, provider_type, limit_per_provider=20)
            candidates_by_provider[provider_type] = candidates
        except Exception as e:
            logger.exception("Failed to discover candidates for %s: %s", provider_type, e)
            candidates_by_provider[provider_type] = []

    context = {
        "workspace": workspace,
        "terms": terms,
        "candidates_by_provider": candidates_by_provider,
    }

    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/source_discover.html", context)
    return render(request, "canopyresearch/source_discover.html", context)


@login_required
@require_http_methods(["POST"])
def workspace_ingest(request, workspace_id):
    """Trigger background ingestion for a workspace. Returns HTMX partial."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    task_ingest_workspace.enqueue(workspace_id=workspace.id)
    context = {"workspace": workspace}
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/ingest_button.html", context)
    messages.success(request, "Ingestion started.")
    return redirect("workspace_detail", workspace_id=workspace.id)


@login_required
def ingestion_log(request, workspace_id):
    """Recent ingestion log entries for a workspace. HTMX polling endpoint."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    from django.utils import timezone

    cutoff = timezone.now() - timedelta(minutes=10)
    base_qs = IngestionLog.objects.filter(source__workspace=workspace).select_related("source")
    running = base_qs.filter(finished_at__isnull=True, started_at__gte=cutoff).exists()
    logs = base_qs.order_by("-started_at")[:20]
    context = {"workspace": workspace, "logs": logs, "running": running}
    return render(request, "canopyresearch/partials/ingestion_log.html", context)


@login_required
@require_http_methods(["POST"])
def workspace_reembed(request, workspace_id):
    """Trigger background re-embedding for all documents in a workspace."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    task_reembed_workspace.enqueue(workspace_id=workspace.id)
    messages.success(
        request, "Re-embedding started. Clustering and scoring will follow automatically."
    )
    return redirect("source_list", workspace_id=workspace.id)


@login_required
def document_list(request, workspace_id):
    """List documents for a workspace. Returns partial for HTMX, full shell otherwise."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    documents = workspace.documents.prefetch_related("sources")

    # Get sort parameter (default to relevance)
    sort_by = request.GET.get("sort", "relevance")
    if sort_by == "relevance":
        documents = documents.order_by("-relevance", "-published_at")
    elif sort_by == "velocity":
        documents = documents.order_by("-velocity", "-published_at")
    elif sort_by == "novelty":
        documents = documents.order_by("-novelty", "-published_at")
    elif sort_by == "published":
        documents = documents.order_by("-published_at")
    else:
        documents = documents.order_by("-relevance", "-published_at")

    # Get filter parameter
    filter_type = request.GET.get("filter", "all")
    if filter_type == "high_relevance":
        # Only show documents with relevance >= 0.5
        documents = documents.filter(relevance__gte=0.5)
    elif filter_type == "low_relevance":
        # Only show documents with relevance < 0.5
        documents = documents.filter(relevance__lt=0.5)
    elif filter_type == "emerging":
        # High novelty + decent alignment (exploration mode)
        documents = documents.filter(novelty__gte=0.6, alignment__gte=0.0)

    context = {
        "workspace": workspace,
        "documents": documents,
        "sort_by": sort_by,
        "filter_type": filter_type,
    }
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/documents_panel.html", context)
    context["tab_content_template"] = "canopyresearch/partials/documents_panel.html"
    context["active_tab"] = "documents"
    return render(request, "canopyresearch/workspace_detail.html", context)


@login_required
def document_detail(request, workspace_id, document_id):
    """Show detail page for a single document."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    document = get_object_or_404(
        Document.objects.prefetch_related("sources"),
        pk=document_id,
        workspace=workspace,
    )

    extracted_links = document.metadata.get("extracted_links", []) if document.metadata else []

    existing_feedback = (
        WorkspaceCoreFeedback.objects.filter(
            workspace=workspace, document=document, user=request.user
        )
        .order_by("-created_at")
        .first()
    )
    existing_vote = existing_feedback.vote if existing_feedback else None

    context = {
        "workspace": workspace,
        "document": document,
        "extracted_links": extracted_links,
        "existing_vote": existing_vote,
    }
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/document_detail.html", context)
    context["tab_content_template"] = "canopyresearch/partials/document_detail.html"
    context["active_tab"] = "documents"
    return render(request, "canopyresearch/workspace_detail.html", context)


@login_required
@require_http_methods(["POST"])
def document_feedback(request, workspace_id, document_id):
    """
    Add thumbs up/down feedback for a document.

    HTMX endpoint that updates core centroid and returns updated document card.
    """
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    document = get_object_or_404(Document, pk=document_id, workspace=workspace)

    vote = request.POST.get("vote")
    if vote not in ["up", "down"]:
        return HttpResponse("Invalid vote", status=400)

    try:
        add_core_feedback(workspace, document, vote, user=request.user)
        # Trigger background task to update core centroid
        task_update_workspace_core.enqueue(workspace_id=workspace.id)
        # Update search terms if thumbs up
        if vote == "up":
            update_search_terms_from_feedback(workspace, document)

        if request.headers.get("HX-Request"):
            context = {"workspace": workspace, "document": document, "existing_vote": vote}
            return render(request, "canopyresearch/partials/document_feedback.html", context)
        messages.success(request, f"Feedback recorded: {vote}")
        return redirect("document_detail", workspace_id=workspace.id, document_id=document.id)
    except ValueError as e:
        if request.headers.get("HX-Request"):
            return HttpResponse(str(e), status=400)
        messages.error(request, str(e))
        return redirect("document_list", workspace_id=workspace.id)


@login_required
@require_http_methods(["GET", "POST"])
def workspace_core_seed(request, workspace_id):
    """
    Show core seed candidates and allow manual seeding.

    GET: Show seed candidates
    POST: Trigger seeding
    """
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)

    if request.method == "POST":
        num_seeds = int(request.POST.get("num_seeds", 5))
        seeded_docs = seed_workspace_core(workspace, num_seeds=num_seeds)
        task_update_workspace_core.enqueue(workspace_id=workspace.id)
        messages.success(request, f"Seeded {len(seeded_docs)} documents as core.")
        if request.headers.get("HX-Request"):
            return redirect("workspace_core_seed", workspace_id=workspace.id)
        return redirect("workspace_detail", workspace_id=workspace.id)

    # GET: Show seed candidates
    seed_docs = workspace.core_seeds.select_related("document").all()
    # Get documents with embeddings for potential seeding
    candidates = workspace.documents.exclude(embedding=[])[:20]

    context = {
        "workspace": workspace,
        "seed_docs": seed_docs,
        "candidates": candidates,
    }
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/core_seed_panel.html", context)
    context["tab_content_template"] = "canopyresearch/partials/core_seed_panel.html"
    context["active_tab"] = "core"
    return render(request, "canopyresearch/workspace_detail.html", context)


@login_required
def cluster_list(request, workspace_id):
    """List clusters for a workspace. Returns partial for HTMX, full shell otherwise."""
    from canopyresearch.services.clustering import compute_cluster_rank

    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)

    # Get all clusters
    all_clusters = list(workspace.clusters.all())

    # Compute rank for each cluster and sort by rank
    clusters_with_rank = [(cluster, compute_cluster_rank(cluster)) for cluster in all_clusters]
    clusters_with_rank.sort(key=lambda x: x[1], reverse=True)  # Sort by rank descending

    # Get filter parameter
    filter_type = request.GET.get("filter", "all")
    if filter_type == "on_topic":
        # Only show clusters with alignment >= 0.3
        clusters_with_rank = [
            (c, r) for c, r in clusters_with_rank if c.alignment is not None and c.alignment >= 0.3
        ]

    # Separate clusters with more than one document from single-document clusters
    # Pass rank with cluster for template rendering (as dict for easier template access)
    multi_doc_clusters = [{"cluster": c, "rank": r} for c, r in clusters_with_rank if c.size > 1]
    single_doc_clusters = [{"cluster": c, "rank": r} for c, r in clusters_with_rank if c.size == 1]

    # Check if map view is requested
    view_type = request.GET.get("view", "list")

    context = {
        "workspace": workspace,
        "clusters": multi_doc_clusters,  # Only show multi-doc clusters by default
        "single_doc_clusters": single_doc_clusters,  # Single-doc clusters for disclosure
        "view_type": view_type,
        "filter_type": filter_type,
    }
    if request.headers.get("HX-Request"):
        if view_type == "map":
            return render(request, "canopyresearch/partials/cluster_map.html", context)
        return render(request, "canopyresearch/partials/clusters_panel.html", context)
    context["tab_content_template"] = "canopyresearch/partials/clusters_panel.html"
    context["active_tab"] = "clusters"
    return render(request, "canopyresearch/workspace_detail.html", context)


@login_required
def cluster_map_json(request, workspace_id):
    """Return JSON data for cluster map visualization, with PCA-projected 2D positions."""

    from canopyresearch.services.clustering import compute_cluster_rank

    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    clusters = list(workspace.clusters.exclude(centroid=[]).filter(size__gt=1).order_by("id"))

    workspace.core_centroid.get("vector") if workspace.core_centroid else None

    # Project cluster centroids to 2D using PCA (numpy only, no sklearn).
    # This places semantically similar clusters near each other on the chart.
    positions = _pca_positions(clusters)

    cluster_data = []
    for cluster, (px, py) in zip(clusters, positions, strict=False):
        alignment = cluster.alignment if cluster.alignment is not None else 0.0
        cluster_data.append(
            {
                "id": cluster.id,
                "label": cluster.label or None,
                "size": cluster.size,
                "alignment": alignment,
                "velocity": cluster.velocity if cluster.velocity is not None else 0.0,
                "drift_distance": cluster.drift_distance,
                "rank": compute_cluster_rank(cluster),
                "position": {"x": px, "y": py},
                "created_at": cluster.created_at.isoformat() if cluster.created_at else None,
                "updated_at": cluster.updated_at.isoformat() if cluster.updated_at else None,
            }
        )

    return JsonResponse(
        {
            "workspace": {"id": workspace.id, "name": workspace.name},
            "clusters": cluster_data,
        }
    )


def _pca_positions(clusters) -> list[tuple[float, float]]:
    """
    Project cluster centroids to 2D via PCA using numpy.

    Returns a list of (x, y) tuples in the same order as the input clusters.
    Falls back to (0, 0) for any cluster missing a centroid.
    """
    import numpy as np

    if not clusters:
        return []

    vectors = []
    valid_idx = []
    for i, c in enumerate(clusters):
        if c.centroid and len(c.centroid) > 0:
            vectors.append(c.centroid)
            valid_idx.append(i)

    result = [(0.0, 0.0)] * len(clusters)

    n = len(vectors)
    if n == 0:
        return result
    if n == 1:
        result[valid_idx[0]] = (0.0, 0.0)
        return result

    X = np.array(vectors, dtype=float)
    X -= X.mean(axis=0)  # centre

    if n == 2:
        # Only one meaningful direction — project onto it
        diff = X[1] - X[0]
        norm = np.linalg.norm(diff)
        if norm > 0:
            u = diff / norm
        else:
            u = np.zeros_like(diff)
            u[0] = 1.0
        proj = X @ u
        for local_i, global_i in enumerate(valid_idx):
            result[global_i] = (float(proj[local_i]), 0.0)
        return result

    # Full PCA: take top-2 eigenvectors of the covariance matrix
    cov = np.cov(X.T)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    # eigh returns ascending order — take the last two (largest variance)
    pc1 = eigenvectors[:, -1]
    pc2 = eigenvectors[:, -2]
    projected = X @ np.column_stack([pc1, pc2])

    for local_i, global_i in enumerate(valid_idx):
        result[global_i] = (float(projected[local_i, 0]), float(projected[local_i, 1]))

    return result


@login_required
def cluster_detail(request, workspace_id, cluster_id):
    """Show cluster details with member documents. HTMX-enabled side panel or modal."""
    from canopyresearch.services.utils import cosine_similarity

    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    cluster = get_object_or_404(
        Cluster.objects.prefetch_related("memberships__document"),
        pk=cluster_id,
        workspace=workspace,
    )

    # Get cluster members
    memberships = cluster.memberships.select_related("document").order_by("-assigned_at")
    documents = [m.document for m in memberships]

    # Get workspace core centroid
    core_centroid = workspace.core_centroid.get("vector") if workspace.core_centroid else None
    cluster_centroid = cluster.centroid if cluster.centroid else []

    # Compute similarity scores for each document
    document_similarities = []
    for membership in memberships:
        document = membership.document
        cluster_similarity = None
        core_similarity = None

        if document.embedding:
            if cluster_centroid:
                try:
                    cluster_similarity = cosine_similarity(document.embedding, cluster_centroid)
                except Exception:
                    cluster_similarity = None

            if core_centroid:
                try:
                    core_similarity = cosine_similarity(document.embedding, core_centroid)
                except Exception:
                    core_similarity = None

        document_similarities.append(
            {
                "document": document,
                "membership": membership,
                "cluster_similarity": cluster_similarity,
                "core_similarity": core_similarity,
            }
        )

    context = {
        "workspace": workspace,
        "cluster": cluster,
        "documents": documents,
        "memberships": memberships,
        "document_similarities": document_similarities,
    }
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/cluster_detail.html", context)
    return render(request, "canopyresearch/cluster_detail.html", context)


@login_required
def cluster_detail_json(request, workspace_id, cluster_id):
    """JSON endpoint for cluster details (for AJAX/HTMX)."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    cluster = get_object_or_404(Cluster, pk=cluster_id, workspace=workspace)

    from canopyresearch.services.clustering import compute_cluster_rank

    # Get cluster members
    memberships = cluster.memberships.select_related("document").order_by("-assigned_at")
    documents = [
        {
            "id": m.document.id,
            "title": m.document.title,
            "url": m.document.url,
            "published_at": m.document.published_at.isoformat()
            if m.document.published_at
            else None,
            "assigned_at": m.assigned_at.isoformat() if m.assigned_at else None,
            "relevance": m.document.relevance,
            "alignment": m.document.alignment,
            "velocity": m.document.velocity,
            "novelty": m.document.novelty,
        }
        for m in memberships
    ]

    rank = compute_cluster_rank(cluster)

    response_data = {
        "id": cluster.id,
        "workspace_id": workspace.id,
        "size": cluster.size,
        "alignment": cluster.alignment,
        "velocity": cluster.velocity,
        "drift_distance": cluster.drift_distance,
        "rank": rank,
        "centroid": cluster.centroid,
        "created_at": cluster.created_at.isoformat() if cluster.created_at else None,
        "updated_at": cluster.updated_at.isoformat() if cluster.updated_at else None,
        "metrics_updated_at": cluster.metrics_updated_at.isoformat()
        if cluster.metrics_updated_at
        else None,
        "documents": documents,
    }

    return JsonResponse(response_data)


@login_required
@require_http_methods(["POST"])
def cluster_branch(request, workspace_id, cluster_id):
    """
    Create a new workspace seeded from this cluster's top documents by relevance.
    """
    from canopyresearch.models import WorkspaceCoreSeed
    from canopyresearch.services.core import update_workspace_core_centroid

    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    cluster = get_object_or_404(Cluster, pk=cluster_id, workspace=workspace)

    name = (
        request.POST.get("name", "").strip() or f"Branch of {workspace.name} (cluster {cluster.id})"
    )

    # Top documents by relevance; fall back to assignment order if unscored
    seed_memberships = list(
        cluster.memberships.select_related("document")
        .filter(document__relevance__isnull=False)
        .order_by("-document__relevance")[:10]
    ) or list(cluster.memberships.select_related("document").order_by("-assigned_at")[:10])

    new_workspace = Workspace.objects.create(
        name=name,
        description=f"Branched from cluster {cluster.id} in '{workspace.name}'.",
        owner=request.user,
    )

    for membership in seed_memberships:
        WorkspaceCoreSeed.objects.create(
            workspace=new_workspace,
            document=membership.document,
            seed_source="manual",
        )

    update_workspace_core_centroid(new_workspace)
    initialize_workspace_search_terms(new_workspace)

    messages.success(
        request, f'Created workspace "{new_workspace.name}" from cluster {cluster.id}.'
    )
    return redirect("source_list", workspace_id=new_workspace.id)
