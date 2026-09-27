"""Top-level URLs.

Every top-level segment added here must also be in apps/core/slugs.RESERVED_SLUGS, so it can
never collide with a profile slug; tests/test_urls.py enforces this.
"""

from django.urls import path
from django.views.generic import TemplateView

from apps.core.views import healthz

urlpatterns = [
    # A placeholder until Phase 4 renders the real home page from data.
    path("", TemplateView.as_view(template_name="placeholder.html"), name="home"),
    path("healthz/", healthz, name="healthz"),
]
