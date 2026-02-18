"""
Django views for canopyresearch.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from canopyresearch.forms import SourceForm, WorkspaceForm
from canopyresearch.models import Document, Source, Workspace
from canopyresearch.services.core import add_core_feedback, seed_workspace_core
from canopyresearch.tasks import task_ingest_workspace, task_update_workspace_core


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
            messages.success(request, f'Workspace "{workspace.name}" created successfully.')
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
def document_list(request, workspace_id):
    """List documents for a workspace. Returns partial for HTMX, full shell otherwise."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    documents = workspace.documents.prefetch_related("sources").order_by("-published_at")

    context = {
        "workspace": workspace,
        "documents": documents,
    }
    if request.headers.get("HX-Request"):
        return render(request, "canopyresearch/partials/documents_panel.html", context)
    context["tab_content_template"] = "canopyresearch/partials/documents_panel.html"
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
        # Trigger background task to update core (in case of batch updates)
        task_update_workspace_core.enqueue(workspace_id=workspace.id)

        if request.headers.get("HX-Request"):
            # Return updated document card
            context = {"workspace": workspace, "document": document}
            return render(request, "canopyresearch/partials/document_card.html", context)
        messages.success(request, f"Feedback recorded: {vote}")
        return redirect("document_list", workspace_id=workspace.id)
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
    candidates = workspace.documents.filter(embedding__len__gt=0).exclude(embedding=[])[:20]

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
