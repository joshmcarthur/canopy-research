"""
Management command for scheduled ingestion.

Checks all workspaces with a configured ingestion_interval_hours and enqueues
ingestion for any that are overdue. Intended to be run periodically via cron
or a docker compose scheduled service.

Usage:
    python manage.py ingest_due
    python manage.py ingest_due --dry-run

Cron example (every 30 minutes):
    */30 * * * * cd /app && python manage.py ingest_due

Docker compose example:
    services:
      scheduler:
        build: .
        command: sh -c 'while true; do python manage.py ingest_due; sleep 1800; done'
        environment: *app-env
"""

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone


class Command(BaseCommand):
    help = "Enqueue ingestion for workspaces that are due based on their ingestion_interval_hours."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report which workspaces are due without enqueuing tasks.",
        )

    def handle(self, *args, **options):
        from canopyresearch.models import Workspace
        from canopyresearch.tasks import task_ingest_workspace

        dry_run = options["dry_run"]
        now = timezone.now()

        # Only consider workspaces with a schedule configured
        workspaces = Workspace.objects.filter(ingestion_interval_hours__isnull=False).annotate(
            last_ingested=Max("sources__last_fetched")
        )

        due = []
        for ws in workspaces:
            interval = ws.ingestion_interval_hours
            last = ws.last_ingested

            if last is None:
                # Never ingested — always due
                due.append((ws, "never ingested"))
            else:
                elapsed_hours = (now - last).total_seconds() / 3600
                if elapsed_hours >= interval:
                    due.append(
                        (ws, f"{elapsed_hours:.1f}h since last ingest (interval: {interval}h)")
                    )

        if not due:
            self.stdout.write("No workspaces due for ingestion.")
            return

        for ws, reason in due:
            if dry_run:
                self.stdout.write(f"[dry-run] Would enqueue: {ws.name} ({reason})")
            else:
                task_ingest_workspace.enqueue(workspace_id=ws.id)
                self.stdout.write(
                    self.style.SUCCESS(f"Enqueued ingestion for: {ws.name} ({reason})")
                )
