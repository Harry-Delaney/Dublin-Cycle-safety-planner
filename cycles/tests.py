from django.contrib.auth import get_user_model
from django.contrib.gis.geos import LineString, MultiPolygon, Point, Polygon
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Area, BikeStation, CycleLane, HazardReport

LNG, LAT = -6.2592, 53.3473


class BikeStationAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        BikeStation.objects.create(station_id="1", name="Close empty", available_bikes=0,
                                   location=Point(LNG + 0.001, LAT, srid=4326))
        BikeStation.objects.create(station_id="2", name="Medium", available_bikes=4,
                                   location=Point(LNG + 0.01, LAT, srid=4326))
        BikeStation.objects.create(station_id="3", name="Far", available_bikes=9,
                                   location=Point(LNG + 0.05, LAT, srid=4326))

    def test_list_is_feature_collection(self):
        response = self.client.get("/api/stations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "FeatureCollection")
        self.assertEqual(len(response.data["features"]), 3)

    def test_nearest_orders_by_distance(self):
        response = self.client.get("/api/stations/nearest/", {"lat": LAT, "lng": LNG})
        names = [f["properties"]["name"] for f in response.data["features"]]
        self.assertEqual(names, ["Close empty", "Medium", "Far"])
        self.assertAlmostEqual(response.data["features"][0]["properties"]["distance_m"], 66, delta=5)

    def test_nearest_uses_metres_not_degrees(self):
        north = BikeStation.objects.create(station_id="N", name="North",
                                           location=Point(LNG, LAT + 0.004, srid=4326))
        east = BikeStation.objects.create(station_id="E", name="East",
                                          location=Point(LNG + 0.006, LAT, srid=4326))
        nearest = list(BikeStation.objects.filter(pk__in=[north.pk, east.pk])
                       .nearest(Point(LNG, LAT, srid=4326), limit=2))
        self.assertEqual(nearest, [east, north])

    def test_nearest_with_bikes_skips_empty_station(self):
        response = self.client.get(
            "/api/stations/nearest/", {"lat": LAT, "lng": LNG, "has_bikes": "true", "limit": 1}
        )
        names = [f["properties"]["name"] for f in response.data["features"]]
        self.assertEqual(names, ["Medium"])

    def test_nearest_requires_coordinates(self):
        response = self.client.get("/api/stations/nearest/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nearest_rejects_out_of_range_coordinates(self):
        response = self.client.get("/api/stations/nearest/", {"lat": 95, "lng": LNG})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class HazardReportAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="pw")
        cls.bob = User.objects.create_user("bob", password="pw")

        CycleLane.objects.create(name="Test lane", geometry=LineString(
            (LNG, LAT - 0.01), (LNG, LAT + 0.01), srid=4326))

        cls.near = HazardReport.objects.create(hazard_type="pothole", reported_by=cls.alice,
                                               location=Point(LNG + 0.0005, LAT, srid=4326))
        cls.far = HazardReport.objects.create(hazard_type="obstruction", reported_by=cls.bob,
                                              location=Point(LNG + 0.005, LAT, srid=4326))

    def test_near_lanes_uses_metres(self):
        response = self.client.get("/api/hazards/near_lanes/")
        ids = [f["id"] for f in response.data["features"]]
        self.assertEqual(ids, [self.near.id])

        response = self.client.get("/api/hazards/near_lanes/", {"distance": 500})
        self.assertEqual(len(response.data["features"]), 2)

    def test_nearby(self):
        response = self.client.get("/api/hazards/nearby/", {"lat": LAT, "lng": LNG, "distance": 100})
        ids = [f["id"] for f in response.data["features"]]
        self.assertEqual(ids, [self.near.id])

    def test_distance_must_be_in_range(self):
        response = self.client.get("/api/hazards/near_lanes/", {"distance": 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get("/api/hazards/nearby/", {"lat": LAT, "lng": LNG, "distance": "far"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_type(self):
        response = self.client.get("/api/hazards/", {"hazard_type": "obstruction"})
        ids = [f["id"] for f in response.data["features"]]
        self.assertEqual(ids, [self.far.id])

    def test_anonymous_cannot_create(self):
        response = self.client.post("/api/hazards/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_sets_reporter(self):
        self.client.force_authenticate(self.alice)
        response = self.client.post("/api/hazards/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["properties"]["reported_by"], "alice")

    def test_only_reporter_can_edit(self):
        self.client.force_authenticate(self.bob)
        response = self.client.patch(f"/api/hazards/{self.near.id}/", {"description": "x"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.alice)
        response = self.client.delete(f"/api/hazards/{self.near.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def _payload(self):
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [LNG, LAT]},
            "properties": {"hazard_type": "dangerous_junction", "description": "Blind corner"},
        }


class AreaAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        def square(x, y, size=0.01):
            return MultiPolygon(Polygon.from_bbox((x, y, x + size, y + size)), srid=4326)

        Area.objects.create(name="Busy", geometry=square(LNG, LAT))
        Area.objects.create(name="Quiet", geometry=square(LNG + 0.02, LAT))
        for offset in (0.002, 0.004, 0.006):
            HazardReport.objects.create(hazard_type="pothole",
                                        location=Point(LNG + offset, LAT + 0.005, srid=4326))

    def test_hazard_counts(self):
        response = self.client.get("/api/areas/hazard_counts/")
        counts = {f["properties"]["name"]: f["properties"]["hazard_count"]
                  for f in response.data["features"]}
        self.assertEqual(counts, {"Busy": 3, "Quiet": 0})
        self.assertEqual(response.data["features"][0]["properties"]["name"], "Busy")
