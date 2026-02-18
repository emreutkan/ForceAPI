"""
Custom rate limiting/throttling classes for different endpoint types.
"""
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle, ScopedRateThrottle


class BurstRateThrottle(UserRateThrottle):
    """
    Throttle for burst requests (short-term rate limiting).
    Used for endpoints that should have strict limits.
    """
    scope = 'burst'


class SustainedRateThrottle(UserRateThrottle):
    """
    Throttle for sustained requests (long-term rate limiting).
    Used for endpoints that need protection against abuse over time.
    """
    scope = 'sustained'


class AnonBurstRateThrottle(AnonRateThrottle):
    """
    Throttle for anonymous burst requests.
    """
    scope = 'anon_burst'


class AnonSustainedRateThrottle(AnonRateThrottle):
    """
    Throttle for anonymous sustained requests.
    """
    scope = 'anon_sustained'


class ProUserRateThrottle(UserRateThrottle):
    """
    Higher rate limits for PRO users.
    """
    scope = 'pro_user'


class CheckDateRateThrottle(UserRateThrottle):
    """
    Rate limiting for check-date / check previous workout endpoints.
    Prevents abuse when polling or scanning many dates.
    """
    scope = 'check_date'
