from django.contrib.gis.geos import Point
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_gis.filters import InBBoxFilter

from .filters import BikeStationFilter, CycleLaneFilter, HazardReportFilter
from .models import Area, BikeStation, CycleLane, HazardReport
from .permissions import IsReporterOrReadOnly
from .serializers import (
    AreaSerializer,
    AreaStatsSerializer,
    BikeStationDistanceSerializer,
    BikeStationSerializer,
    CycleLaneSerializer,
    HazardReportDistanceSerializer,
    HazardReportSerializer,
)


def error_response(message):
    return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


def parse_search_point(data):
    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return None, error_response("Provide numeric lat and lng values.")

    if not -90 <= lat <= 90 or not -180 <= lng <= 180:
        return None, error_response(
            "Latitude must be between -90 and 90 and longitude between -180 and 180."
        )
    return Point(lng, lat, srid=4326), None


# Reads a number (e.g. distance or limit) from the request, using a default if missing.
# It must be above 0 and no more than the maximum.
def parse_number(data, name, default, maximum):
    try:
        value = float(data.get(name, default))
    except (TypeError, ValueError):
        return None, error_response(f"{name} must be a number.")

    if not 0 < value <= maximum:
        return None, error_response(f"{name} must be greater than 0 and no more than {maximum}.")
    return value, None


class BikeStationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BikeStation.objects.all()
    serializer_class = BikeStationSerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend, InBBoxFilter]
    filterset_class = BikeStationFilter
    bbox_filter_field = "location"

    
    # Closest stations to a point, with the distance to each
    @action(detail=False, methods=["get"])
    def nearest(self, request):
        point, error = parse_search_point(request.query_params)
        if error:
            return error
        limit, error = parse_number(request.query_params, "limit", 5, 50)
        if error:
            return error

        # Apply any filters first (e.g. has_bikes=true), then find the nearest
        stations = self.filter_queryset(self.get_queryset()).nearest(point, int(limit))
        return Response(BikeStationDistanceSerializer(stations, many=True).data)


# Hazard reports at /api/hazards/
# Anyone can view them; logged-in users can add them; only the reporter can edit or delete
class HazardReportViewSet(viewsets.ModelViewSet):
    queryset = HazardReport.objects.select_related("reported_by")
    serializer_class = HazardReportSerializer
    pagination_class = None
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsReporterOrReadOnly]
    filter_backends = [DjangoFilterBackend, InBBoxFilter]
    filterset_class = HazardReportFilter
    bbox_filter_field = "location"

    # Record the logged-in user as the reporter of a new hazard
    def perform_create(self, serializer):
        serializer.save(reported_by=self.request.user)

    @action(detail=False, methods=["get"])
    def nearby(self, request):
        point, error = parse_search_point(request.query_params)
        if error:
            return error
        distance, error = parse_number(request.query_params, "distance", 500, 5000)
        if error:
            return error

        hazards = self.filter_queryset(self.get_queryset()).within_distance(point, distance)
        return Response(HazardReportDistanceSerializer(hazards, many=True).data)

    # /api/hazards/near_lanes/?distance=50
    # Hazards within a distance (in metres) of any cycle lane
    @action(detail=False, methods=["get"])
    def near_lanes(self, request):
        distance, error = parse_number(request.query_params, "distance", 50, 1000)
        if error:
            return error

        hazards = self.filter_queryset(self.get_queryset()).near_lanes(distance)
        return Response(self.get_serializer(hazards, many=True).data)


class CycleLaneViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CycleLane.objects.all()
    serializer_class = CycleLaneSerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend, InBBoxFilter]
    filterset_class = CycleLaneFilter
    bbox_filter_field = "geometry"
    bbox_filter_include_overlapping = True  # Include lanes that are partly inside the box


class AreaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    pagination_class = None
    filter_backends = [InBBoxFilter]
    bbox_filter_field = "geometry"
    bbox_filter_include_overlapping = True

    # Hazard count and cycle lane length for every area
    def areas_with_stats(self):
        return self.filter_queryset(self.get_queryset()).with_hazard_counts().with_lane_lengths()

    # /api/areas/hazard_counts/
    # Every area with the number of hazards inside it, most hazards first
    @action(detail=False, methods=["get"])
    def hazard_counts(self, request):
        areas = self.areas_with_stats().order_by("-hazard_count", "name")
        return Response(AreaStatsSerializer(areas, many=True).data)

    # /api/areas/lane_lengths/
    # Every area with the length of cycle lane inside it, most lanes first
    @action(detail=False, methods=["get"])
    def lane_lengths(self, request):
        areas = self.areas_with_stats().order_by("-lane_length", "name")
        return Response(AreaStatsSerializer(areas, many=True).data)


# The map page. ensure_csrf_cookie gives the browser the token map.js needs
# to send when reporting, editing or deleting hazards.
@ensure_csrf_cookie
def index(request):
    user = request.user
    context = {
        "total_stations": BikeStation.objects.count(),
        "total_hazards": HazardReport.objects.count(),
        "total_lanes": CycleLane.objects.count(),
        "total_areas": Area.objects.count(),
        "hazard_types": HazardReport.HazardType.choices,
        "lane_types": CycleLane.LaneType.choices,
        # Who is logged in, passed to map.js so it knows whether to show edit/delete buttons
        "map_config": {
            "isAuthenticated": user.is_authenticated,
            "username": user.get_username() if user.is_authenticated else None,
            "isStaff": user.is_staff,
        },
    }
    return render(request, "cycles/index.html", context)
