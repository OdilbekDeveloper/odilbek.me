"""Read access to core data (the hard rule: public reads go through selectors)."""

from apps.core.models import SiteSettings


def site_settings():
    """The site settings row, or an unsaved blank one. Reading never creates the row."""
    return SiteSettings.objects.filter(pk=1).first() or SiteSettings()
