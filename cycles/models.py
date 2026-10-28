from django.conf import settings
from django.contrib.gis.db import models


class BikeStation(models.Model):
    station_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    capacity = models.PositiveIntegerField(default=0)
    available_bikes = models.PositiveIntegerField(default=0)
    available_stands = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(null=True, blank=True)
    location = models.PointField(srid=4326)

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

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
