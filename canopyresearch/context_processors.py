"""
Context processors for canopyresearch.
"""

from canopyresearch.models import Workspace


def workspace_context(request):
    """Provide workspaces and active_workspace for all authenticated pages."""
    if not request.user.is_authenticated:
        return {"workspaces": [], "active_workspace": None}

    workspaces = list(Workspace.objects.filter(owner=request.user).order_by("name"))

    active_workspace = None
    try:
        from django.urls import resolve

        match = resolve(request.path)
        workspace_id = match.kwargs.get("workspace_id")
        if workspace_id:
            active_workspace = Workspace.objects.filter(pk=workspace_id, owner=request.user).first()
    except Exception:
        pass

    return {
        "workspaces": workspaces,
        "active_workspace": active_workspace,
    }
