from django.db import migrations

from canopyresearch.services.source_discovery import initialize_workspace_search_terms
from canopyresearch.services.term_extraction import extract_terms_from_document, extract_terms_from_text


def populate_search_terms(apps, schema_editor):
    """
    Extract and populate search terms from existing workspaces and feedback.

    - Extract terms from workspace names and descriptions
    - Extract terms from thumbs-up documents
    """
    Workspace = apps.get_model("canopyresearch", "Workspace")
    WorkspaceCoreFeedback = apps.get_model("canopyresearch", "WorkspaceCoreFeedback")
    WorkspaceSearchTerms = apps.get_model("canopyresearch", "WorkspaceSearchTerms")
    Document = apps.get_model("canopyresearch", "Document")

    # Term weights
    TERM_WEIGHTS = {
        "name": 2.0,
        "description": 1.5,
        "document": 1.0,
    }

    # Process each workspace
    for workspace in Workspace.objects.all():
        # Extract from workspace name
        if workspace.name:
            name_terms = extract_terms_from_text(workspace.name)
            for term in name_terms:
                WorkspaceSearchTerms.objects.update_or_create(
                    workspace=workspace,
                    term=term,
                    defaults={
                        "source": "name",
                        "weight": TERM_WEIGHTS["name"],
                    },
                )

        # Extract from workspace description
        if workspace.description:
            desc_terms = extract_terms_from_text(workspace.description)
            for term in desc_terms:
                WorkspaceSearchTerms.objects.update_or_create(
                    workspace=workspace,
                    term=term,
                    defaults={
                        "source": "description",
                        "weight": TERM_WEIGHTS["description"],
                    },
                )

        # Extract from thumbs-up documents
        thumbs_up_feedback = WorkspaceCoreFeedback.objects.filter(
            workspace=workspace, vote="up"
        ).select_related("document")

        for feedback in thumbs_up_feedback:
            try:
                doc_terms = extract_terms_from_document(feedback.document)
                weight = TERM_WEIGHTS["document"]
                for term in doc_terms:
                    WorkspaceSearchTerms.objects.update_or_create(
                        workspace=workspace,
                        term=term,
                        defaults={
                            "source": "document",
                            "weight": weight,
                            "document": feedback.document,
                        },
                    )
            except Exception:
                # Skip if document doesn't exist or extraction fails
                continue


def reverse_populate_search_terms(apps, schema_editor):
    """Remove all search terms (cleanup for migration rollback)."""
    WorkspaceSearchTerms = apps.get_model("canopyresearch", "WorkspaceSearchTerms")
    WorkspaceSearchTerms.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('canopyresearch', '0007_workspace_search_terms'),
    ]

    operations = [
        migrations.RunPython(populate_search_terms, reverse_populate_search_terms),
    ]
