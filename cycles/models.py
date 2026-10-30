
from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis.db.models.functions import Distance, GeometryDistance
from django.contrib.gis.measure import D
from django.db.models import Exists, F, Func, IntegerField, OuterRef, Subquery


# Spatial queries for each model [Week 5, Django docs]


class BikeStationQuerySet(models.QuerySet):
    def with_bikes(self):
        return self.filter(available_bikes__gt=0)

    # Nearest stations to a point [Django docs, PostGIS docs]
    def nearest(self, point, limit=5):
        candidates = self.order_by(GeometryDistance("location", point)).values("pk")[: limit * 4]
        return (
            self.model.objects.filter(pk__in=candidates)
            .annotate(distance=Distance("location", point))
            .order_by("distance")[:limit]
        )


class HazardReportQuerySet(models.QuerySet):
    # Hazards within a distance of a point, closest first [Week 5]
    def within_distance(self, point, metres):
        return (
            self.filter(location__distance_lte=(point, D(m=metres)))
            .annotate(distance=Distance("location", point))
            .order_by("distance")
        )

    # Hazards within a distance of any cycle lane [Week 5, Django docs]
    def near_lanes(self, metres):
        lanes_nearby = CycleLane.objects.filter(
            geometry__distance_lte=(OuterRef("location"), D(m=metres))
        )
        return self.filter(Exists(lanes_nearby))


class AreaQuerySet(models.QuerySet):
    # Number of hazards inside each area [Django docs, Week 5]
    def with_hazard_counts(self):
        hazards_inside = (
            HazardReport.objects.filter(location__within=OuterRef("geometry"))
            .order_by()
            .annotate(count=Func(F("id"), function="COUNT"))
            .values("count")
        )
        return self.annotate(hazard_count=Subquery(hazards_inside, output_field=IntegerField()))


class BikeStation(models.Model):
    station_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    capacity = models.PositiveIntegerField(default=0)
    available_bikes = models.PositiveIntegerField(default=0)
    available_stands = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(null=True, blank=True)
    location = models.PointField(srid=4326)

    objects = BikeStationQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class HazardReport(models.Model):
    class HazardType(models.TextChoices):
        POTHOLE = "pothole", "Pothole"
        POOR_VISIBILITY = "poor_visibility", "Poor visibility on turn"
        DANGEROUS_JUNCTION = "dangerous_junction", "Dangerous junction"
        OBSTRUCTION = "obstruction", "Obstruction"
        OTHER = "other", "Other"

    hazard_type = models.CharField(max_length=30, choices=HazardType.choices)
    description = models.TextField(blank=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hazard_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    location = models.PointField(srid=4326)

    objects = HazardReportQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_hazard_type_display()} ({self.created_at:%Y-%m-%d})"


class CycleLane(models.Model):
    class LaneType(models.TextChoices):
        SEGREGATED = "segregated", "Segregated"
        PAINTED = "painted", "Painted"
        SHARED = "shared", "Shared / bus lane"
        GREENWAY = "greenway", "Greenway"
        OTHER = "other", "Other"

    name = models.CharField(max_length=200, blank=True)
    lane_type = models.CharField(
        max_length=20, choices=LaneType.choices, default=LaneType.OTHER
    )
    source = models.CharField(max_length=100, blank=True)
    geometry = models.LineStringField(srid=4326)

    def __str__(self):
        return self.name or f"Cycle lane {self.pk}"


class Area(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True)
    geometry = models.MultiPolygonField(srid=4326)

    objects = AreaQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
