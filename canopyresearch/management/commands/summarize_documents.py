"""
Management command to backfill summaries for documents that don't have one yet.

A document is considered summarisable when it has non-empty content.
By default only processes documents with an empty summary.
Pass --all to re-summarise documents that already have a summary.
Pass --workspace <id> to limit to a single workspace.

Usage:
    python manage.py summarize_documents
    python manage.py summarize_documents --all
    python manage.py summarize_documents --workspace 3
    python manage.py summarize_documents --all --workspace 3
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Backfill summaries for documents that are summarisable but have none."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            dest="resummarise",
            help="Re-summarise documents that already have a summary.",
        )
        parser.add_argument(
            "--workspace",
            type=int,
            metavar="ID",
            help="Limit to a single workspace.",
        )

    def handle(self, *args, **options):
        from canopyresearch.models import Document
        from canopyresearch.services.summarization import summarize_document

        qs = Document.objects.select_related("workspace").exclude(content="")

        if options["workspace"]:
            qs = qs.filter(workspace_id=options["workspace"])

        if not options["resummarise"]:
            qs = qs.filter(summary="")

        total = qs.count()
        if total == 0:
            self.stdout.write("No documents to summarise.")
            return

        self.stdout.write(f"Summarising {total} document(s)...")

        success = 0
        skipped = 0
        errors = 0

        for doc in qs.iterator():
            try:
                summary = summarize_document(doc)
                if summary:
                    doc.summary = summary
                    doc.save(update_fields=["summary", "updated_at"])
                    success += 1
                else:
                    skipped += 1
            except Exception as e:
                self.stderr.write(f"Error summarising document {doc.id} ({doc.title!r}): {e}")
                errors += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {success} summarised, {skipped} skipped (LLM unavailable), {errors} errors."
            )
        )
