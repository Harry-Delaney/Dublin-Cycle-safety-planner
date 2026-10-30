from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load all open datasets from data/ (areas, then lanes clipped to them, then stations)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Loading Cycle Safe open data...\n"))

        # Areas first, as lanes are cut to their boundary
        self.stdout.write("🗺️  Loading areas...")
        call_command("load_areas")

        self.stdout.write("\n🚴 Loading cycle lanes...")
        call_command("load_lanes")

        self.stdout.write("\n🚲 Loading bike stations...")
        call_command("load_stations")

        self.stdout.write(
            self.style.SUCCESS(
                "\n🎉 Data loading complete!"
                "\n\n💡 You can now:"
                "\n   - View the map at http://localhost:8000/"
                "\n   - Test API endpoints at http://localhost:8000/api/"
                "\n   - View admin interface at http://localhost:8000/admin/"
            )
        )
