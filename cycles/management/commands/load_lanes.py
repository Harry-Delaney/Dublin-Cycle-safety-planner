from django.conf import settings
from django.contrib.gis.db.models import Union
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import LineString, MultiLineString
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cycles.models import Area, CycleLane

DEFAULT_PATH = settings.BASE_DIR / "data" / "cycle_network.geojson"
SOURCE = "NTA Cycle Network 2025"

# NTA lane types -> our lane types and popup labels
LANE_TYPES = {
    "BIKE_LANE": (CycleLane.LaneType.PAINTED, "Bike lane"),
    "CYCLE_LANE": (CycleLane.LaneType.PAINTED, "Bike lane"),
    "SEPARATE_TRAIL": (CycleLane.LaneType.SEGREGATED, "Segregated cycle track"),
    "SHARED_ROAD": (CycleLane.LaneType.SHARED, "Shared road"),
    "NON_TRAFFIC_TRAIL": (CycleLane.LaneType.GREENWAY, "Off-road trail"),
    "BIKE_FRIENDLY_PEDESTRIAN_PATH": (CycleLane.LaneType.OTHER, "Bike-friendly path"),
}


# Splits a cut lane into its separate line pieces
def line_parts(geom):
    if isinstance(geom, LineString):
        yield geom
    elif isinstance(geom, MultiLineString) or geom.geom_type == "GeometryCollection":
        for part in geom:
            yield from line_parts(part)


class Command(BaseCommand):
    help = "Load the NTA cycle network, clipped to the Dublin City boundary (run load_areas first)"

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(DEFAULT_PATH), help="GeoJSON file to load")

    @transaction.atomic
    def handle(self, *args, **options):
        # Merge the areas into one Dublin City boundary
        boundary = Area.objects.aggregate(boundary=Union("geometry"))["boundary"]
        if boundary is None:
            raise CommandError("No areas loaded. Run `python manage.py load_areas` first.")
        prepared_boundary = boundary.prepared

        # Clear old lanes so there are no duplicates
        deleted, _ = CycleLane.objects.filter(source=SOURCE).delete()
        if deleted:
            self.stdout.write(f"Cleared {deleted} existing {SOURCE} lanes")

        self.stdout.write(f"Loading lanes from {options['path']}...")
        layer = DataSource(options["path"])[0]

        # Keep only lanes inside the city, cut at the boundary
        lanes, outside, unknown_types = [], 0, set()
        for feature in layer:
            geom = feature.geom.geos
            geom.srid = 4326
            if not prepared_boundary.intersects(geom):
                outside += 1
                continue

            bike_type = feature.get("BIKE")
            if bike_type not in LANE_TYPES:
                unknown_types.add(bike_type)
            lane_type, label = LANE_TYPES.get(bike_type, (CycleLane.LaneType.OTHER, "Cycle route"))
            direction = (feature.get("DIR") or "").lower()
            name = f"{label} ({direction})" if direction else label

            clipped = geom.intersection(boundary)
            for part in line_parts(clipped):
                part.srid = 4326
                lanes.append(CycleLane(name=name, lane_type=lane_type, source=SOURCE, geometry=part))

        CycleLane.objects.bulk_create(lanes, batch_size=1000)

        if unknown_types:
            self.stdout.write(self.style.WARNING(f"Unknown BIKE values loaded as 'other': {unknown_types}"))
        self.stdout.write(f"Skipped {outside} lanes outside Dublin City")
        self.stdout.write(self.style.SUCCESS(f"✓ {len(lanes)} lanes loaded inside Dublin City"))
