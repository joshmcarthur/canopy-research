"""
Django management command for populating the database with initial data.

This command runs automatically on container startup if RUN_SEEDS=true.
You can also run it manually: python manage.py seed
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Management command to seed the database."""

    help = "Populate the database with initial data"

    def handle(self, *args, **options):
        """Run seed operations."""
        self.stdout.write("Running seed command...")

        # Example: Create a superuser if it doesn't exist
        # Uncomment and modify as needed:
        # from django.contrib.auth import get_user_model
        # User = get_user_model()
        # if not User.objects.filter(username="admin").exists():
        #     User.objects.create_superuser(
        #         username="admin",
        #         email="admin@example.com",
        #         password="changeme"
        #     )
        #     self.stdout.write(self.style.SUCCESS("Created admin superuser"))

        # Example: Load fixtures
        # from django.core.management import call_command
        # call_command("loaddata", "initial_data.json")

        self.stdout.write(self.style.SUCCESS("Seed command completed."))
