from django.urls import include, path, re_path

from trips.views import api_not_found

urlpatterns = [
    path("api/", include("trips.urls")),
    re_path(r"^api/.*$", api_not_found),
]
