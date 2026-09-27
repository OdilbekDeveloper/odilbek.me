"""Top-level URLs.

Every top-level segment added here must also be in apps/core/slugs.RESERVED_SLUGS, so it can
never collide with a profile slug; tests/test_urls.py enforces this.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

from apps.core.views import healthz

urlpatterns = [
    # A placeholder until Phase 4 renders the real home page from data.
    path("", TemplateView.as_view(template_name="placeholder.html"), name="home"),
    path("healthz/", healthz, name="healthz"),
]

# The temporary content editor. Off in production until Phase 5 puts it behind allauth + MFA.
if settings.ADMIN_ENABLED:
    urlpatterns.append(path(settings.ADMIN_URL, admin.site.urls))

# Uploaded media in local development only (static() returns nothing unless DEBUG). Production
# serves media from object storage (Phase 10), never from the app.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
