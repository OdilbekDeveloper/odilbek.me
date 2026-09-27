"""URL segments a profile slug may never take.

Role profiles live at the URL root (/developer/, D-012), so a profile slug must not collide with a
language prefix or with any route the site defines. The profile slug validator (Phase 2) rejects
these; tests/test_urls.py fails when a top-level route exists that is missing from this list.
"""

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
