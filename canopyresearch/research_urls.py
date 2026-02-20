"""
URL configuration for research views.
"""

from django.urls import path

from canopyresearch import views

urlpatterns = [
    path("", views.workspace_create, name="workspace_create"),
    path("workspaces/create/", views.workspace_create, name="workspace_create"),
    # More specific routes must come before the catch-all workspace_detail route
    path(
        "workspaces/<int:workspace_id>/edit/",
        views.workspace_edit,
        name="workspace_edit",
    ),
    path(
        "workspaces/<int:workspace_id>/delete/",
        views.workspace_delete,
        name="workspace_delete",
    ),
    path(
        "workspaces/<int:workspace_id>/switch/",
        views.workspace_switch,
        name="workspace_switch",
    ),
    path("workspaces/<int:workspace_id>/", views.workspace_detail, name="workspace_detail"),
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
    path(
        "workspaces/<int:workspace_id>/documents/<int:document_id>/feedback/",
        views.document_feedback,
        name="document_feedback",
    ),
    path(
        "workspaces/<int:workspace_id>/core/",
        views.workspace_core_seed,
        name="workspace_core_seed",
    ),
    path(
        "workspaces/<int:workspace_id>/ingest/",
        views.workspace_ingest,
        name="workspace_ingest",
    ),
    path(
        "workspaces/<int:workspace_id>/clusters/",
        views.cluster_list,
        name="cluster_list",
    ),
    path(
        "workspaces/<int:workspace_id>/clusters/map.json",
        views.cluster_map_json,
        name="cluster_map_json",
    ),
    path(
        "workspaces/<int:workspace_id>/clusters/<int:cluster_id>/",
        views.cluster_detail,
        name="cluster_detail",
    ),
    path(
        "workspaces/<int:workspace_id>/clusters/<int:cluster_id>/json/",
        views.cluster_detail_json,
        name="cluster_detail_json",
    ),
]
