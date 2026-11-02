from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AreaViewSet, BikeStationViewSet, CycleLaneViewSet, HazardReportViewSet

# The router creates the list and detail URLs for each viewset,
# e.g. /api/hazards/ and /api/hazards/5/
router = DefaultRouter()
router.register(r"stations", BikeStationViewSet)
router.register(r"hazards", HazardReportViewSet)
router.register(r"lanes", CycleLaneViewSet)
router.register(r"areas", AreaViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
