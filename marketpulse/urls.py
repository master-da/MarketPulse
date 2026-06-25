"""Top-level URL configuration for MarketPulse."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("marketpulse.api_urls")),
    path("", include("dashboard.urls")),
]
