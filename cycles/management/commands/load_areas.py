from django.conf import settings
from django.contrib.gis.utils import LayerMapping
from django.core.management.base import BaseCommand
from django.db import transaction

from cycles.models import Area

DEFAULT_PATH = settings.BASE_DIR / "data" / "electoral_divisions.geojson"

# File fields -> Area fields
AREA_MAPPING = {
    "name": "Pllng_D",   # Division name
    "code": "Lcl_E_A",   # Electoral area
    "geometry": "MULTIPOLYGON",
}


class Command(BaseCommand):
    help = "Load Dublin City electoral divisions (Smart Dublin / DCC open data) as Areas"

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(DEFAULT_PATH), help="GeoJSON file to load")

    @transaction.atomic
    def handle(self, *args, **options):
        # Clear old areas so there are no duplicates
        deleted, _ = Area.objects.all().delete()
        if deleted:
            self.stdout.write(f"Cleared {deleted} existing areas")

        self.stdout.write(f"Loading areas from {options['path']}...")
        lm = LayerMapping(Area, options["path"], AREA_MAPPING, transform=True)
        lm.save(strict=True, verbose=False)

        self.stdout.write(self.style.SUCCESS(f"✓ {Area.objects.count()} areas in database"))
