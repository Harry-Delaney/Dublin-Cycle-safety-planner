from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.gdal import DataSource
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cycles.models import HazardReport

DEFAULT_PATH = settings.BASE_DIR / "data" / "sample_hazards.geojson"


class Command(BaseCommand):
    help = "Load sample hazard reports for the demo (run create_demo_user first)"

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(DEFAULT_PATH), help="GeoJSON file to load")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all hazards reported by the demo user before loading",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # The sample hazards are reported by the demo account
        User = get_user_model()
        try:
            demo = User.objects.get(username="demo")
        except User.DoesNotExist:
            raise CommandError("No demo user. Run `python manage.py create_demo_user` first.")

        if options["clear"]:
            self.stdout.write("Clearing demo hazards...")
            HazardReport.objects.filter(reported_by=demo).delete()
            self.stdout.write(self.style.SUCCESS("✓ Demo hazards cleared"))

        self.stdout.write(f"Loading sample hazards from {options['path']}...")
        layer = DataSource(options["path"])[0]

        created_count = 0
        skipped_count = 0

        for feature in layer:
            point = feature.geom.geos
            point.srid = 4326

            # Skip hazards that were already loaded, so re-running adds no duplicates
            hazard, created = HazardReport.objects.get_or_create(
                reported_by=demo,
                description=feature.get("description"),
                defaults={"hazard_type": feature.get("hazard_type"), "location": point},
            )

            if created:
                created_count += 1
            else:
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nData loading complete!\n"
                f"Created: {created_count} hazards\n"
                f"Already loaded: {skipped_count} hazards\n"
                f"Total: {HazardReport.objects.count()} hazards in database"
            )
        )
