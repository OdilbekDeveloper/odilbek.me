import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@never_cache
@require_safe
def healthz(request):
    """Liveness plus database reachability, for the platform's health check.

    A deploy whose database is unreachable fails its health check and never receives traffic.
    The response says nothing about why: details go to the log, not to an anonymous caller.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        logger.exception("Health check could not reach the database")
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
