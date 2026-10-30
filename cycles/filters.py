from django_filters import rest_framework as filters

from .models import BikeStation, CycleLane, HazardReport


class BikeStationFilter(filters.FilterSet):
    has_bikes = filters.BooleanFilter(method="filter_has_bikes")
    has_stands = filters.BooleanFilter(method="filter_has_stands")
    min_bikes = filters.NumberFilter(field_name="available_bikes", lookup_expr="gte")

    class Meta:
        model = BikeStation
        fields = {"name": ["icontains"]}

    def filter_has_bikes(self, queryset, name, value):
        if value:
            return queryset.with_bikes()
        return queryset

    def filter_has_stands(self, queryset, name, value):
        if value:
            return queryset.filter(available_stands__gt=0)
        return queryset


class HazardReportFilter(filters.FilterSet):
    hazard_type = filters.MultipleChoiceFilter(choices=HazardReport.HazardType.choices)
    reported_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    reported_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    mine = filters.BooleanFilter(method="filter_mine")

    class Meta:
        model = HazardReport
        fields = {"description": ["icontains"]}

    def filter_mine(self, queryset, name, value):
        if value and self.request.user.is_authenticated:
            return queryset.filter(reported_by=self.request.user)
        return queryset


class CycleLaneFilter(filters.FilterSet):
    lane_type = filters.MultipleChoiceFilter(choices=CycleLane.LaneType.choices)

    class Meta:
        model = CycleLane
        fields = {"name": ["icontains"], "source": ["exact"]}
