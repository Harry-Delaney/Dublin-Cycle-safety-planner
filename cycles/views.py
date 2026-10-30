from django.contrib.gis.geos import Point
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_gis.filters import InBBoxFilter

from .filters import BikeStationFilter, CycleLaneFilter, HazardReportFilter
from .models import Area, BikeStation, CycleLane, HazardReport
from .permissions import IsReporterOrReadOnly
from .serializers import (
    AreaHazardCountSerializer,
    AreaSerializer,
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

    @action(detail=False, methods=["get"])
    def nearest(self, request):
        point, error = parse_search_point(request.query_params)
        if error:
            return error
        limit, error = parse_number(request.query_params, "limit", 5, 50)
        if error:
            return error

        stations = self.filter_queryset(self.get_queryset()).nearest(point, int(limit))
        return Response(BikeStationDistanceSerializer(stations, many=True).data)


class HazardReportViewSet(viewsets.ModelViewSet):
    queryset = HazardReport.objects.select_related("reported_by")
    serializer_class = HazardReportSerializer
    pagination_class = None
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsReporterOrReadOnly]
    filter_backends = [DjangoFilterBackend, InBBoxFilter]
    filterset_class = HazardReportFilter
    bbox_filter_field = "location"

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
    bbox_filter_include_overlapping = True


class AreaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    pagination_class = None
    filter_backends = [InBBoxFilter]
    bbox_filter_field = "geometry"
    bbox_filter_include_overlapping = True

    @action(detail=False, methods=["get"])
    def hazard_counts(self, request):
        areas = (
            self.filter_queryset(self.get_queryset())
            .with_hazard_counts()
            .order_by("-hazard_count", "name")
        )
        return Response(AreaHazardCountSerializer(areas, many=True).data)

