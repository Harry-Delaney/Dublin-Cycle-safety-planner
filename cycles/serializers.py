from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import Area, BikeStation, CycleLane, HazardReport


class BikeStationSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = BikeStation
        geo_field = "location"
        fields = [
            "id", "station_id", "name", "capacity", "available_bikes",
            "available_stands", "last_updated",
        ]


# Bike station plus its distance in metres from the search point (used by "nearest")
class BikeStationDistanceSerializer(BikeStationSerializer):

    distance_m = serializers.SerializerMethodField()

    class Meta(BikeStationSerializer.Meta):
        fields = BikeStationSerializer.Meta.fields + ["distance_m"]

    def get_distance_m(self, obj):
        return round(obj.distance.m, 1)


class HazardReportSerializer(GeoFeatureModelSerializer):
    # Show the reporter's username, set automatically rather than sent by the user
    reported_by = serializers.StringRelatedField(read_only=True)
    # Readable hazard type, e.g. "Dangerous junction" instead of "dangerous_junction"
    hazard_type_display = serializers.CharField(
        source="get_hazard_type_display", read_only=True
    )

    class Meta:
        model = HazardReport
        geo_field = "location"
        fields = [
            "id", "hazard_type", "hazard_type_display", "description",
            "reported_by", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


# Hazard report plus its distance in metres from the search point (used by "nearby")
class HazardReportDistanceSerializer(HazardReportSerializer):

    distance_m = serializers.SerializerMethodField()

    class Meta(HazardReportSerializer.Meta):
        fields = HazardReportSerializer.Meta.fields + ["distance_m"]

    def get_distance_m(self, obj):
        return round(obj.distance.m, 1)


class CycleLaneSerializer(GeoFeatureModelSerializer):
    # Readable lane type, e.g. "Segregated"
    lane_type_display = serializers.CharField(
        source="get_lane_type_display", read_only=True
    )

    class Meta:
        model = CycleLane
        geo_field = "geometry"
        fields = ["id", "name", "lane_type", "lane_type_display", "source"]


class AreaSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Area
        geo_field = "geometry"
        fields = ["id", "name", "code"]


# Area plus the number of hazards inside it (used by "hazard_counts")
class AreaHazardCountSerializer(AreaSerializer):

    hazard_count = serializers.IntegerField(read_only=True)

    class Meta(AreaSerializer.Meta):
        fields = AreaSerializer.Meta.fields + ["hazard_count"]
