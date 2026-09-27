"""URL segments a profile slug may never take.

Role profiles live at the URL root (/developer/, D-012), so a profile slug must not collide with a
language prefix or with any route the site defines. The profile slug validator (Phase 2) rejects
these; tests/test_urls.py fails when a top-level route exists that is missing from this list.
"""

from django.conf import settings
from django.core.exceptions import ValidationError

LANGUAGE_PREFIXES = frozenset({"en", "ko", "uz"})

ROUTE_SEGMENTS = frozenset(
    {
        "about",
        "projects",
        "skills",
        "map",
        "resume",
        "contact",
        "privacy",
        "blog",
        "dashboard",
        "accounts",
        "admin",
        "e",
        "api",
        "static",
        "media",
        "healthz",
        "sitemap.xml",
        "robots.txt",
        ".well-known",
        "_styleguide",
    }
)

RESERVED_SLUGS = LANGUAGE_PREFIXES | ROUTE_SEGMENTS


def admin_segment():
    """The admin's configured top-level segment (DJANGO_ADMIN_PATH), e.g. 'admin'."""
    return settings.ADMIN_URL.strip("/")


def is_reserved(slug):
    """Reserved for a route or language, including the admin path configured for this
    environment. The database enforces RESERVED_SLUGS; only this can see the admin path."""
    return slug in RESERVED_SLUGS or slug == admin_segment()


def validate_not_reserved(value):
    if is_reserved(value):
        raise ValidationError(
            f"'{value}' is reserved for a site route or language and cannot be a profile slug.",
            code="reserved_slug",
        )
