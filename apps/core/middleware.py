from django.conf import settings


def build_permissions_policy(policy):
    """Render {"camera": [], "fullscreen": ["self"]} as 'camera=(), fullscreen=(self)'."""
    return ", ".join(f"{feature}=({' '.join(allow)})" for feature, allow in policy.items())


class PermissionsPolicyMiddleware:
    """Send the Permissions-Policy header, which Django has no setting for."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.header = build_permissions_policy(settings.PERMISSIONS_POLICY)

    def __call__(self, request):
        response = self.get_response(request)
        if self.header:
            response.headers.setdefault("Permissions-Policy", self.header)
        return response
