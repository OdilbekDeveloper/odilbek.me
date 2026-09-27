"""Every top-level URL segment is reserved, so no profile slug can ever shadow a route (D-012)."""

from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver
from django.urls.resolvers import LocalePrefixPattern

from apps.core.slugs import LANGUAGE_PREFIXES, RESERVED_SLUGS


def top_level_segments(patterns):
    for entry in patterns:
        if isinstance(entry, URLResolver) and isinstance(entry.pattern, LocalePrefixPattern):
            # i18n_patterns (Phase 4): the language prefix is reserved separately; look inside.
            yield from top_level_segments(entry.url_patterns)
            continue
        assert isinstance(entry, URLPattern | URLResolver)
        segment = str(entry.pattern).lstrip("^").split("/")[0]
        if segment:
            yield segment


def test_every_top_level_route_segment_is_reserved():
    unreserved = set(top_level_segments(get_resolver().url_patterns)) - RESERVED_SLUGS
    assert not unreserved, (
        f"Add {sorted(unreserved)} to apps/core/slugs.py so no profile slug can take them."
    )


def test_every_configured_language_prefix_is_reserved():
    assert {code for code, _ in settings.LANGUAGES} <= LANGUAGE_PREFIXES
