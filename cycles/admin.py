from django.contrib.gis import admin

from .models import Area, BikeStation, CycleLane, HazardReport

# Centre the admin map widgets on Dublin
DUBLIN_MAP = {"default_lon": -6.26, "default_lat": 53.35, "default_zoom": 12}


@admin.register(BikeStation)
class BikeStationAdmin(admin.GISModelAdmin):
    list_display = ("name", "station_id", "capacity", "available_bikes", "last_updated")
    search_fields = ("name", "station_id")
    gis_widget_kwargs = {"attrs": DUBLIN_MAP}


@admin.register(HazardReport)
class HazardReportAdmin(admin.GISModelAdmin):
    list_display = ("hazard_type", "reported_by", "created_at")
    list_filter = ("hazard_type",)
    search_fields = ("description",)
    readonly_fields = ("created_at", "updated_at")
    gis_widget_kwargs = {"attrs": DUBLIN_MAP}


@admin.register(CycleLane)
class CycleLaneAdmin(admin.GISModelAdmin):
    list_display = ("__str__", "lane_type", "source")
    list_filter = ("lane_type",)
    gis_widget_kwargs = {"attrs": DUBLIN_MAP}


@admin.register(Area)
class AreaAdmin(admin.GISModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
    gis_widget_kwargs = {"attrs": DUBLIN_MAP}
