"""
Management command to enqueue label generation for clusters.

By default enqueues all clusters with size >= 2 that have no label yet.
Pass --all to re-label clusters that already have a label.
Pass --workspace <id> to limit to a single workspace.

Usage:
    python manage.py label_clusters
    python manage.py label_clusters --all
    python manage.py label_clusters --workspace 3
    python manage.py label_clusters --all --workspace 3
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Enqueue background label generation for clusters."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            dest="relabel",
            help="Re-label clusters that already have a label.",
        )
        parser.add_argument(
            "--workspace",
            type=int,
            metavar="ID",
            help="Limit to a single workspace.",
        )

    def handle(self, *args, **options):
        from canopyresearch.models import Cluster
        from canopyresearch.tasks import task_label_cluster

        qs = Cluster.objects.filter(size__gte=2)

        if options["workspace"]:
            qs = qs.filter(workspace_id=options["workspace"])

        if not options["relabel"]:
            qs = qs.filter(label="")

        total = qs.count()
        if total == 0:
            self.stdout.write("No clusters to label.")
            return

        for cluster in qs:
            task_label_cluster.enqueue(cluster_id=cluster.id)

        self.stdout.write(self.style.SUCCESS(f"Enqueued labeling for {total} cluster(s)."))
