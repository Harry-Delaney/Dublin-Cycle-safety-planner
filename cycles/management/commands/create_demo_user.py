import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update the demo account used as test credentials (not an admin)"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo", help="Username for the demo account")

    def handle(self, *args, **options):
        # The password comes from .env, not the code
        password = os.environ.get("DEMO_USER_PASSWORD")
        if not password:
            raise CommandError("Set DEMO_USER_PASSWORD in .env first.")

        # Create the account, or reset its password if it already exists
        User = get_user_model()
        user, created = User.objects.get_or_create(username=options["username"])
        user.set_password(password)
        user.is_staff = False
        user.is_superuser = False
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"✓ {action} demo user '{user.username}'"))
