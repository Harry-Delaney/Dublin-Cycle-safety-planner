import os

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load all data from data/ (areas, lanes, stations, then the demo user and sample hazards)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Loading Cycle Safe open data...\n"))

        # Areas first, as lanes are cut to their boundary
        self.stdout.write("🗺️  Loading areas...")
        call_command("load_areas")

        self.stdout.write("\n🚴 Loading cycle lanes...")
        call_command("load_lanes")

        self.stdout.write("\n🚲 Loading bike stations...")
        call_command("load_stations")

        # The demo account and its sample hazards are only added if a demo password is set
        if os.environ.get("DEMO_USER_PASSWORD"):
            self.stdout.write("\n👤 Creating demo user...")
            call_command("create_demo_user")

            self.stdout.write("\n⚠️  Loading sample hazards...")
            call_command("load_sample_hazards")
        else:
            self.stdout.write("\nSkipping demo user and sample hazards (DEMO_USER_PASSWORD not set)")

        self.stdout.write(
            self.style.SUCCESS(
                "\n🎉 Data loading complete!"
                "\n\n💡 You can now:"
                "\n   - View the map at http://localhost:8000/"
                "\n   - Test API endpoints at http://localhost:8000/api/"
                "\n   - View admin interface at http://localhost:8000/admin/"
            )
        )
