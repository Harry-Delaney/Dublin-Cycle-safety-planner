from datetime import datetime, timezone

from django.conf import settings
from django.contrib.gis.gdal import DataSource
from django.core.management.base import BaseCommand
from django.db import transaction

from cycles.models import BikeStation

DEFAULT_PATH = settings.BASE_DIR / "data" / "stations.geojson"


class Command(BaseCommand):
    help = "Load Dublin Bikes stations (Smart Dublin / DCC open data)"

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(DEFAULT_PATH), help="GeoJSON file to load")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing stations before loading",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing stations...")
            BikeStation.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("✓ Existing stations cleared"))

        self.stdout.write(f"Loading stations from {options['path']}...")
        layer = DataSource(options["path"])[0]

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for feature in layer:
            # Skip uninstalled stations and copy the fields across
            if not feature.get("is_installed"):
                skipped_count += 1
                continue

            point = feature.geom.geos
            point.srid = 4326
            last_reported = feature.get("last_reported")

            station, created = BikeStation.objects.update_or_create(
                station_id=str(feature.get("station_id")),
                defaults={
                    "name": feature.get("name").title(),
                    "capacity": feature.get("capacity") or 0,
                    "available_bikes": feature.get("num_bikes_available") or 0,
                    "available_stands": feature.get("num_docks_available") or 0,
                    "last_updated": (
                        datetime.fromtimestamp(last_reported, tz=timezone.utc) if last_reported else None
                    ),
                    "location": point,
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nData loading complete!\n"
                f"Created: {created_count} stations\n"
                f"Updated: {updated_count} stations\n"
                f"Skipped (not installed): {skipped_count}\n"
                f"Total: {BikeStation.objects.count()} stations in database"
            )
        )
