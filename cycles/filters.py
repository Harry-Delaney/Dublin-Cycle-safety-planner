from django_filters import rest_framework as filters

from .models import BikeStation, CycleLane, HazardReport

# Filters let the API narrow results with URL options, e.g. /api/stations/?has_bikes=true


# Bike station filters
class BikeStationFilter(filters.FilterSet):
    has_bikes = filters.BooleanFilter(method="filter_has_bikes")    # ?has_bikes=true
    has_stands = filters.BooleanFilter(method="filter_has_stands")  # ?has_stands=true
    min_bikes = filters.NumberFilter(field_name="available_bikes", lookup_expr="gte")  # ?min_bikes=3

    class Meta:
        model = BikeStation
        fields = {"name": ["icontains"]}  # ?name__icontains=street

    # Only stations with at least one bike
    def filter_has_bikes(self, queryset, name, value):
        if value:
            return queryset.with_bikes()
        return queryset

    # Only stations with at least one free stand to return a bike to
    def filter_has_stands(self, queryset, name, value):
        if value:
            return queryset.filter(available_stands__gt=0)
        return queryset


# Hazard report filters
class HazardReportFilter(filters.FilterSet):
    # One or more types, e.g. ?hazard_type=pothole&hazard_type=obstruction
    hazard_type = filters.MultipleChoiceFilter(choices=HazardReport.HazardType.choices)
    # Reported within a date range
    reported_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    reported_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    mine = filters.BooleanFilter(method="filter_mine")  # ?mine=true

    class Meta:
        model = HazardReport
        fields = {"description": ["icontains"]}  # Search the description text

    # Only hazards reported by the logged-in user
    def filter_mine(self, queryset, name, value):
        if value and self.request.user.is_authenticated:
            return queryset.filter(reported_by=self.request.user)
        return queryset


# Cycle lane filters
class CycleLaneFilter(filters.FilterSet):
    # One or more lane types, e.g. ?lane_type=segregated
    lane_type = filters.MultipleChoiceFilter(choices=CycleLane.LaneType.choices)

    class Meta:
        model = CycleLane
        fields = {"name": ["icontains"], "source": ["exact"]}
