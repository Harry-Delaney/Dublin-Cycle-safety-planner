import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import LineString, MultiPolygon, Point, Polygon
from django.core.management import CommandError, call_command
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Area, BikeStation, CycleLane, HazardReport

# Test location used throughout: O'Connell Bridge, Dublin
LNG, LAT = -6.2592, 53.3473


# Bike station endpoints and the "nearest" search
class BikeStationAPITests(APITestCase):
    # Three stations about 70 m, 700 m and 3.5 km east of the test location (one has no bikes)
    @classmethod
    def setUpTestData(cls):
        BikeStation.objects.create(station_id="1", name="Close empty", available_bikes=0,
                                   location=Point(LNG + 0.001, LAT, srid=4326))
        BikeStation.objects.create(station_id="2", name="Medium", available_bikes=4,
                                   location=Point(LNG + 0.01, LAT, srid=4326))
        BikeStation.objects.create(station_id="3", name="Far", available_bikes=9,
                                   location=Point(LNG + 0.05, LAT, srid=4326))

    # The list comes back as GeoJSON with all stations
    def test_list_is_feature_collection(self):
        response = self.client.get("/api/stations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "FeatureCollection")
        self.assertEqual(len(response.data["features"]), 3)

    # Nearest stations are sorted closest first, with distances in metres
    def test_nearest_orders_by_distance(self):
        response = self.client.get("/api/stations/nearest/", {"lat": LAT, "lng": LNG})
        names = [f["properties"]["name"] for f in response.data["features"]]
        self.assertEqual(names, ["Close empty", "Medium", "Far"])
        self.assertAlmostEqual(response.data["features"][0]["properties"]["distance_m"], 66, delta=5)

    # The north station is closer in degrees but the east one is closer in metres;
    # the east one must come first
    def test_nearest_uses_metres_not_degrees(self):
        north = BikeStation.objects.create(station_id="N", name="North",
                                           location=Point(LNG, LAT + 0.004, srid=4326))
        east = BikeStation.objects.create(station_id="E", name="East",
                                          location=Point(LNG + 0.006, LAT, srid=4326))
        nearest = list(BikeStation.objects.filter(pk__in=[north.pk, east.pk])
                       .nearest(Point(LNG, LAT, srid=4326), limit=2))
        self.assertEqual(nearest, [east, north])

    # has_bikes=true skips the empty station
    def test_nearest_with_bikes_skips_empty_station(self):
        response = self.client.get(
            "/api/stations/nearest/", {"lat": LAT, "lng": LNG, "has_bikes": "true", "limit": 1}
        )
        names = [f["properties"]["name"] for f in response.data["features"]]
        self.assertEqual(names, ["Medium"])

    # Missing coordinates give a 400 error
    def test_nearest_requires_coordinates(self):
        response = self.client.get("/api/stations/nearest/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # Impossible coordinates (latitude 95) give a 400 error
    def test_nearest_rejects_out_of_range_coordinates(self):
        response = self.client.get("/api/stations/nearest/", {"lat": 95, "lng": LNG})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# Hazard endpoints, spatial searches and permissions
class HazardReportAPITests(APITestCase):
    # Two users, one north-south cycle lane, and two hazards about 33 m and 330 m from the lane
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

    # Only the hazard within 50 m of the lane is returned; at 500 m both are
    def test_near_lanes_uses_metres(self):
        response = self.client.get("/api/hazards/near_lanes/")
        ids = [f["id"] for f in response.data["features"]]
        self.assertEqual(ids, [self.near.id])

        response = self.client.get("/api/hazards/near_lanes/", {"distance": 500})
        self.assertEqual(len(response.data["features"]), 2)

    # Only hazards within 100 m of the test location are returned
    def test_nearby(self):
        response = self.client.get("/api/hazards/nearby/", {"lat": LAT, "lng": LNG, "distance": 100})
        ids = [f["id"] for f in response.data["features"]]
        self.assertEqual(ids, [self.near.id])

    # Distances of 0 or non-numbers give a 400 error
    def test_distance_must_be_in_range(self):
        response = self.client.get("/api/hazards/near_lanes/", {"distance": 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get("/api/hazards/nearby/", {"lat": LAT, "lng": LNG, "distance": "far"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # Filtering by hazard type
    def test_filter_by_type(self):
        response = self.client.get("/api/hazards/", {"hazard_type": "obstruction"})
        ids = [f["id"] for f in response.data["features"]]
        self.assertEqual(ids, [self.far.id])

    # Logged-out users cannot report hazards
    def test_anonymous_cannot_create(self):
        response = self.client.post("/api/hazards/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # A logged-in user can report a hazard and is recorded as the reporter
    def test_create_sets_reporter(self):
        self.client.force_authenticate(self.alice)
        response = self.client.post("/api/hazards/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["properties"]["reported_by"], "alice")

    # Another user cannot edit the hazard, but the reporter can delete it
    def test_only_reporter_can_edit(self):
        self.client.force_authenticate(self.bob)
        response = self.client.patch(f"/api/hazards/{self.near.id}/", {"description": "x"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.alice)
        response = self.client.delete(f"/api/hazards/{self.near.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    # A new hazard in GeoJSON format, as the map would send it
    def _payload(self):
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [LNG, LAT]},
            "properties": {"hazard_type": "dangerous_junction", "description": "Blind corner"},
        }


# Hazard counts per area
class AreaAPITests(APITestCase):
    # Two square areas side by side, with three hazards inside the first
    @classmethod
    def setUpTestData(cls):
        def square(x, y, size=0.01):
            return MultiPolygon(Polygon.from_bbox((x, y, x + size, y + size)), srid=4326)

        Area.objects.create(name="Busy", geometry=square(LNG, LAT))
        Area.objects.create(name="Quiet", geometry=square(LNG + 0.02, LAT))
        for offset in (0.002, 0.004, 0.006):
            HazardReport.objects.create(hazard_type="pothole",
                                        location=Point(LNG + offset, LAT + 0.005, srid=4326))

    # The busy area has 3 hazards, the quiet one 0, and the busy one is listed first
    def test_hazard_counts(self):
        response = self.client.get("/api/areas/hazard_counts/")
        counts = {f["properties"]["name"]: f["properties"]["hazard_count"]
                  for f in response.data["features"]}
        self.assertEqual(counts, {"Busy": 3, "Quiet": 0})
        self.assertEqual(response.data["features"][0]["properties"]["name"], "Busy")

    # Only the part of a lane inside an area is counted: a lane crossing the whole
    # quiet area (0.01° wide, about 665 m) counts 665 m there and nothing in the busy area
    def test_lane_lengths(self):
        y = LAT + 0.005
        CycleLane.objects.create(name="Crossing", geometry=LineString(
            (LNG + 0.015, y), (LNG + 0.035, y), srid=4326))
        response = self.client.get("/api/areas/lane_lengths/")
        lengths = {f["properties"]["name"]: f["properties"]["lane_length_km"]
                   for f in response.data["features"]}
        self.assertAlmostEqual(lengths["Quiet"], 0.665, delta=0.01)
        self.assertEqual(lengths["Busy"], 0)
        self.assertEqual(response.data["features"][0]["properties"]["name"], "Quiet")


# The map page and login page
class MapPageTests(APITestCase):
    # Logged out: the map loads, shows the login prompt and sets the CSRF cookie
    def test_map_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'id="map"')
        self.assertContains(response, 'id="map-config"')
        self.assertContains(response, "Log in to report")
        self.assertIn("csrftoken", response.cookies)

    # The login page has a username field
    def test_login_page_renders(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'name="username"')

    # Logged in: the report button shows and the username is passed to map.js
    def test_report_button_when_logged_in(self):
        user = get_user_model().objects.create_user("carol", password="pw")
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertContains(response, 'id="report-hazard"')
        self.assertContains(response, '"username": "carol"')


# Data loader tests, using small sample files
class LoadDataCommandTests(APITestCase):

    # Temporary folder for the sample files
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def write_geojson(self, name, features):
        path = Path(self.tmpdir.name) / name
        path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
        return str(path)

    # Loads one small square area
    def load_area(self):
        x, y = LNG, LAT
        ring = [[x, y], [x + 0.01, y], [x + 0.01, y + 0.01], [x, y + 0.01], [x, y]]
        path = self.write_geojson("areas.geojson", [{
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"Pllng_D": "Test Division", "Lcl_E_A": "Test LEA"},
        }])
        call_command("load_areas", path=path, stdout=StringIO())

    # Area is saved with the right fields
    def test_load_areas(self):
        self.load_area()
        area = Area.objects.get()
        self.assertEqual((area.name, area.code), ("Test Division", "Test LEA"))
        self.assertEqual(area.geometry.geom_type, "MultiPolygon")

    # Lanes are cut, split, filtered and not duplicated
    def test_load_lanes_clips_and_splits(self):
        self.load_area()
        y = LAT + 0.005
        path = self.write_geojson("lanes.geojson", [
            {"type": "Feature", "properties": {"BIKE": "BIKE_LANE", "DIR": "Forward"},
             "geometry": {"type": "LineString", "coordinates": [[LNG - 0.01, y], [LNG + 0.02, y]]}},
            {"type": "Feature", "properties": {"BIKE": "SEPARATE_TRAIL", "DIR": "Bi-Directional"},
             "geometry": {"type": "MultiLineString", "coordinates": [
                 [[LNG + 0.001, LAT + 0.001], [LNG + 0.002, LAT + 0.001]],
                 [[LNG + 0.003, LAT + 0.002], [LNG + 0.004, LAT + 0.002]]]}},
            {"type": "Feature", "properties": {"BIKE": "SHARED_ROAD", "DIR": "Forward"},
             "geometry": {"type": "LineString", "coordinates": [[LNG + 1, LAT], [LNG + 1.01, LAT]]}},
        ])
        call_command("load_lanes", path=path, stdout=StringIO())

        self.assertEqual(CycleLane.objects.count(), 3)
        painted = CycleLane.objects.get(lane_type="painted")
        self.assertEqual(painted.name, "Bike lane (forward)")
        self.assertAlmostEqual(painted.geometry.extent[0], LNG, places=6)
        self.assertAlmostEqual(painted.geometry.extent[2], LNG + 0.01, places=6)
        self.assertEqual(CycleLane.objects.filter(lane_type="segregated").count(), 2)

        call_command("load_lanes", path=path, stdout=StringIO())
        self.assertEqual(CycleLane.objects.count(), 3)

    # Lanes need areas loaded first
    def test_load_lanes_needs_areas(self):
        path = self.write_geojson("lanes.geojson", [])
        with self.assertRaises(CommandError):
            call_command("load_lanes", path=path, stdout=StringIO())

    # Stations load, and re-running updates them
    def test_load_stations(self):
        def station(station_id, installed=True, bikes=3):
            return {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [LNG, LAT]},
                "properties": {
                    "station_id": station_id, "name": "CLARENDON ROW", "capacity": 31,
                    "num_bikes_available": bikes, "num_docks_available": 28,
                    "is_installed": installed, "last_reported": 1793365769,
                },
            }

        path = self.write_geojson("stations.geojson", [station("1"), station("2", installed=False)])
        call_command("load_stations", path=path, stdout=StringIO())
        loaded = BikeStation.objects.get()
        self.assertEqual((loaded.station_id, loaded.name, loaded.available_bikes), ("1", "Clarendon Row", 3))
        self.assertIsNotNone(loaded.last_updated)

        path = self.write_geojson("stations.geojson", [station("1", bikes=9)])
        call_command("load_stations", path=path, stdout=StringIO())
        self.assertEqual(BikeStation.objects.get().available_bikes, 9)


# Demo account and sample hazards
@mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": "demo-pass"})
class DemoDataCommandTests(APITestCase):
    # Demo user is a normal account with the password from .env, and is not duplicated
    def test_create_demo_user(self):
        call_command("create_demo_user", stdout=StringIO())
        call_command("create_demo_user", stdout=StringIO())
        demo = get_user_model().objects.get(username="demo")
        self.assertTrue(demo.check_password("demo-pass"))
        self.assertFalse(demo.is_staff or demo.is_superuser)

    # No password set means no demo user
    def test_create_demo_user_needs_password(self):
        with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": ""}):
            with self.assertRaises(CommandError):
                call_command("create_demo_user", stdout=StringIO())

    # Every sample hazard loads once, reported by the demo user
    def test_load_sample_hazards(self):
        call_command("create_demo_user", stdout=StringIO())
        call_command("load_sample_hazards", stdout=StringIO())
        call_command("load_sample_hazards", stdout=StringIO())

        sample_file = Path(__file__).resolve().parent.parent / "data" / "sample_hazards.geojson"
        expected = len(json.loads(sample_file.read_text())["features"])
        self.assertEqual(HazardReport.objects.count(), expected)
        self.assertEqual(HazardReport.objects.exclude(reported_by__username="demo").count(), 0)

    # Sample hazards need the demo user first
    def test_load_sample_hazards_needs_demo_user(self):
        with self.assertRaises(CommandError):
            call_command("load_sample_hazards", stdout=StringIO())
