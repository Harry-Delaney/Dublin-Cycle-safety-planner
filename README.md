# Dublin-Cycle-safety-planner

# Cycle Safe - A Cycle Safety Planner

This is a location-based web application that helps cyclists find bike-share stations, view cycle lanes, and reportavoid road hazards such as potholes, poor visibility on turns, and dangerous junctions.

## Status
**Currently In Development** - The project skeleton has been set up: Django, PostGis and pgAdmin running in Docker containers on an isolated network.
Skeleton and spatial models are done.

## Planned Features

- Interactive Leaflet map showing cycle lanes, bike stations and hazard reports
- Users can add, edit and delete hazard reports by clicking on the app
- Find the nearest bike station with available bikes
- See hazards within a set distance with available bike lanes
- See which area has the most reported hazards
- Responsive design for desktop, tablet and mobile

## Planned Spatial Queries
- **Proximity** - nearest bike stations to the users location ('ST_Distance' / KNN '<->')
- **Buffer / width distance** - hazards within 50m of a cycle lane ('ST_DWithin')
- **Containment** - count of hazards in each aread ('ST_Contains')

## Technology Used or Each Layer
- Database: PostgreSQL + PostGIS
- Backend: Django (GeoDjango) + Django REST Framework
- Frontend: Bootstrap 5, Leaflet JS, OpenStreetMap
- Deployment: Docker, Docker Compose, pgAdmin 4

## Spatial Data Model
| Table          | Geometry    | Description                                |
|----------------|-------------|--------------------------------------------|
| `BikeStation`  | Point       | Bike-share station locations and capacity  |
| `HazardReport` | Point       | User-submitted hazards (type, description) |
| `CycleLane`    | LineString  | Cycle network from open data               |
| `Area`         | MultiPolygon| Local area / electoral boundaries          |

## Setup commands
- git clone <url>
- cd <repo-folder>
- cp .env.example .env
- docker compose up --build

- docker compose exec web python manage.py migrate
- docker compose exec web python manage.py createsuperuser

## Services
- Django app: http://localhost:8000
- Django admin: http://localhost:8000/admin
- pgAdmin: http://localhost:5050

## Data Sources (planned)

- Cycle lanes: NTA / council open data on data.gov.ie, or OpenStreetMap
- Bike stations: bike-share open data API
- Area boundaries: CSO / Tailte Éireann boundary files
- Hazard reports: submitted by users

## Roadmap

- Docker + PostGIS + Django skeleton
- Spatial models and migrations
- Load open data
- REST API endpoints for spatial queries
- Leaflet map front end
- Authentication for hazard reports
- Nginx reverse proxy (optional)
- Screenshots, architecture diagram, user guide
