-- Cycle Safe: spatial queries to run in pgAdmin (Tools > Query Tool on the cyclesafe database).
-- Highlight one query and press F5 to run it. All distances use Portobello Bridge
-- (longitude -6.2652, latitude 53.3306) as the search point.


-- 1. PostGIS version, and the points, lines and polygons stored in each table
-- Expected: 113 stations (POINT), 12 hazards (POINT), 1425 lanes (LINESTRING), 162 areas (MULTIPOLYGON)
SELECT postgis_version();

SELECT 'stations' AS layer, COUNT(*) AS rows, MIN(GeometryType(location)) AS geometry_type FROM cycles_bikestation
UNION ALL SELECT 'hazards', COUNT(*), MIN(GeometryType(location)) FROM cycles_hazardreport
UNION ALL SELECT 'lanes',   COUNT(*), MIN(GeometryType(geometry)) FROM cycles_cyclelane
UNION ALL SELECT 'areas',   COUNT(*), MIN(GeometryType(geometry)) FROM cycles_area;


-- 2. Spatial (GiST) indexes on every geometry column
-- Expected: 4 rows, one per table
SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public' AND indexdef ILIKE '%gist%';


-- 3. Nearest 5 bike stations (KNN)
-- The <-> operator uses the index to pick 10 candidates quickly, but it measures in degrees,
-- so the candidates are re-sorted by real distance in metres.
-- Expected: Lennox Street 88 m, Portobello Road 197 m, Charlemont Place 345 m,
--           Grantham Street 393 m, Hatch Street 484 m
SELECT name, available_bikes, distance_m FROM (
    SELECT name, available_bikes,
           ROUND(ST_DistanceSphere(location, ST_SetSRID(ST_MakePoint(-6.2652, 53.3306), 4326))) AS distance_m
    FROM cycles_bikestation
    ORDER BY location <-> ST_SetSRID(ST_MakePoint(-6.2652, 53.3306), 4326)
    LIMIT 10
) AS candidates
ORDER BY distance_m
LIMIT 5;


-- 4. Hazards within a radius
-- Expected at 500 m: 2 rows (0.0 m pothole, 232.5 m wheelie bins)
-- Change 500 to 1100 for 3 rows, 1200 for 4, 1500 for 5
SELECT hazard_type, description,
       ROUND(ST_DistanceSphere(location, ST_SetSRID(ST_MakePoint(-6.2652, 53.3306), 4326))::numeric, 1) AS distance_m
FROM cycles_hazardreport
WHERE ST_DistanceSphere(location, ST_SetSRID(ST_MakePoint(-6.2652, 53.3306), 4326)) <= 500
ORDER BY distance_m;


-- 5. Hazards within 50 m of a cycle lane
-- Casting to geography makes the 50 mean metres.
-- Expected: 6 rows
SELECT h.hazard_type, h.description
FROM cycles_hazardreport h
WHERE EXISTS (
    SELECT 1 FROM cycles_cyclelane l
    WHERE ST_DWithin(h.location::geography, l.geometry::geography, 50)
);


-- 6. Hazards inside each area (the numbers behind the map colours)
-- Expected: St Kevin's 2, then several areas with 1
SELECT a.name, COUNT(h.id) AS hazards
FROM cycles_area a
LEFT JOIN cycles_hazardreport h ON ST_Within(h.location, a.geometry)
GROUP BY a.name
ORDER BY hazards DESC
LIMIT 10;


-- 7. Kilometres of cycle lane inside each area
-- Each lane is cut to the area boundary before it is measured.
-- Expected: Phoenix Park 24.01, Rathmines East B 7.34, St Kevin's 6.35, Cabra East A 5.70, South Dock 5.16
SELECT a.name,
       ROUND((SUM(ST_Length(ST_Intersection(l.geometry, a.geometry)::geography)) / 1000)::numeric, 2) AS lane_km
FROM cycles_area a
JOIN cycles_cyclelane l ON ST_Intersects(l.geometry, a.geometry)
GROUP BY a.name
ORDER BY lane_km DESC
LIMIT 10;


-- 8. Latest hazard reports (run before and after reporting, editing or deleting one on the map)
SELECT id, hazard_type, description, ST_AsText(location) AS location, created_at, updated_at
FROM cycles_hazardreport
ORDER BY created_at DESC
LIMIT 3;


-- 9. Area shapes for pgAdmin's Geometry Viewer (click the eye icon on the geometry column)
SELECT name, geometry
FROM cycles_area;


-- 10. Query plan for the nearest-station search, to see whether the spatial index is used
-- With only ~100 stations PostgreSQL may choose a plain scan, which is normal for a small table.
EXPLAIN ANALYZE
SELECT name
FROM cycles_bikestation
ORDER BY location <-> ST_SetSRID(ST_MakePoint(-6.2652, 53.3306), 4326)
LIMIT 5;
