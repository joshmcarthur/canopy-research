"""
URL configuration for research views.
"""

from django.urls import path

from canopyresearch import views

urlpatterns = [
    path("", views.workspace_list, name="workspace_list"),
    path("workspaces/", views.workspace_list, name="workspace_list"),
    path("workspaces/create/", views.workspace_create, name="workspace_create"),
    path("workspaces/<int:workspace_id>/", views.workspace_detail, name="workspace_detail"),
    path(
        "workspaces/<int:workspace_id>/switch/",
        views.workspace_switch,
        name="workspace_switch",
    ),
    path(
        "workspaces/<int:workspace_id>/sources/",
        views.source_list,
        name="source_list",
    ),
    path(
        "workspaces/<int:workspace_id>/sources/create/",
        views.source_create,
        name="source_create",
    ),
    path(
        "workspaces/<int:workspace_id>/sources/<int:source_id>/edit/",
        views.source_edit,
        name="source_edit",
    ),
    path(
        "workspaces/<int:workspace_id>/sources/<int:source_id>/delete/",
        views.source_delete,
        name="source_delete",
    ),
    path(
        "workspaces/<int:workspace_id>/documents/",
        views.document_list,
        name="document_list",
    ),
]
