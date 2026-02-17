"""
Django views for canopyresearch.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from canopyresearch.forms import SourceForm, WorkspaceForm
from canopyresearch.models import Source, Workspace


@login_required
def workspace_list(request):
    """Display list of workspaces for the current user."""
    workspaces = Workspace.objects.filter(owner=request.user).annotate(
        sources_count=Count('sources'),
        documents_count=Count('documents')
    )
    context = {
        "workspaces": workspaces,
    }
    return render(request, "canopyresearch/workspace_list.html", context)


@login_required
def workspace_detail(request, workspace_id):
    """Display workspace detail with sources and documents."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    sources = workspace.sources.all()
    documents = workspace.documents.prefetch_related("sources").order_by("-published_at")[:50]

    context = {
        "workspace": workspace,
        "sources": sources,
        "documents": documents,
    }
    return render(request, "canopyresearch/workspace_detail.html", context)


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
            return redirect("workspace_detail", workspace_id=workspace.id)
    else:
        form = WorkspaceForm()

    context = {"form": form}
    return render(request, "canopyresearch/workspace_form.html", context)


@login_required
def source_list(request, workspace_id):
    """List sources for a workspace."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    sources = workspace.sources.all()

    context = {
        "workspace": workspace,
        "sources": sources,
    }
    return render(request, "canopyresearch/source_list.html", context)


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
            if request.headers.get("HX-Request"):
                # HTMX request - return partial
                return render(request, "canopyresearch/source_item.html", {"source": source})
            return redirect("source_list", workspace_id=workspace.id)
    else:
        form = SourceForm(workspace=workspace)

    context = {
        "workspace": workspace,
        "form": form,
    }
    return render(request, "canopyresearch/source_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def source_edit(request, workspace_id, source_id):
    """Edit an existing source."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    source = get_object_or_404(Source, pk=source_id, workspace=workspace)

    if request.method == "POST":
        form = SourceForm(request.POST, instance=source, workspace=workspace)
        if form.is_valid():
            form.save()
            return redirect("source_list", workspace_id=workspace.id)
    else:
        form = SourceForm(instance=source, workspace=workspace)

    context = {
        "workspace": workspace,
        "source": source,
        "form": form,
    }
    return render(request, "canopyresearch/source_form.html", context)


@login_required
@require_http_methods(["POST"])
def source_delete(request, workspace_id, source_id):
    """Delete a source."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    source = get_object_or_404(Source, pk=source_id, workspace=workspace)
    source.delete()

    if request.headers.get("HX-Request"):
        return HttpResponse("")
    return redirect("source_list", workspace_id=workspace.id)


@login_required
def document_list(request, workspace_id):
    """List documents for a workspace."""
    workspace = get_object_or_404(Workspace, pk=workspace_id, owner=request.user)
    documents = workspace.documents.prefetch_related("sources").order_by("-published_at")

    context = {
        "workspace": workspace,
        "documents": documents,
    }
    return render(request, "canopyresearch/document_list.html", context)
