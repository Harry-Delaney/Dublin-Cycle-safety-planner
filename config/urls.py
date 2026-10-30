from django.contrib import admin
from django.urls import include, path

from cycles.views import index

urlpatterns = [
    path("", index, name="index"),  # Map page
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),  # Login and logout pages
    path("api/", include("cycles.urls")),
    path("api-auth/", include("rest_framework.urls")),  # Login/logout for the browsable API
]
