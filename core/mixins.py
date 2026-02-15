"""
Reusable mixins for API views.
"""
from datetime import datetime
from django.utils import timezone
from django.utils.http import http_date, parse_http_date
from rest_framework.response import Response
from rest_framework import status


# 5 minutes in seconds (for Cache-Control max-age and 304 fallback bucket)
CACHE_MAX_AGE_SECONDS = 300


def _round_to_5_minutes(dt):
    """Round datetime down to the start of the current 5-minute bucket (UTC)."""
    ts = int(dt.timestamp())
    bucket = (ts // CACHE_MAX_AGE_SECONDS) * CACHE_MAX_AGE_SECONDS
    return datetime.fromtimestamp(bucket, tz=timezone.utc)


class ConditionalGetMixin:
    """
    Mixin for APIView GET handlers: adds Last-Modified, Cache-Control (5 min),
    and returns 304 Not Modified when the client sends If-Modified-Since and
    the resource has not changed.

    Use as the first base class: class MyView(ConditionalGetMixin, APIView).

    Override get_last_modified(request, *args, **kwargs) to return the resource's
    last modification datetime (timezone-aware), or None to use a 5-minute
    bucket (same Last-Modified for all requests in that window, so clients
    get 304 when re-requesting within 5 minutes).
    """

    def get_last_modified(self, request, *args, **kwargs):
        """
        Return the last modification datetime for this GET resource, or None
        to use a 5-minute time bucket (good for computed/stateless endpoints).
        """
        return None

    def get(self, request, *args, **kwargs):
        last_modified = self.get_last_modified(request, *args, **kwargs)
        if last_modified is None:
            last_modified = _round_to_5_minutes(timezone.now())

        if_modified_since = request.META.get("HTTP_IF_MODIFIED_SINCE")
        if if_modified_since:
            try:
                parsed_ts = parse_http_date(if_modified_since.strip())
                if_modified_dt = datetime.fromtimestamp(parsed_ts, tz=timezone.utc)
                if last_modified <= if_modified_dt:
                    return Response(status=status.HTTP_304_NOT_MODIFIED)
            except (ValueError, TypeError):
                pass

        response = super().get(request, *args, **kwargs)

        if response.status_code == 200:
            response["Last-Modified"] = http_date(int(last_modified.timestamp()))
            response["Cache-Control"] = f"private, max-age={CACHE_MAX_AGE_SECONDS}"

        return response
