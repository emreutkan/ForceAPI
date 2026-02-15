"""
Custom rate limiting/throttling classes for different endpoint types.
"""
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle, ScopedRateThrottle


class DeveloperBypassMixin:
    """
    Mixin that bypasses rate limiting for users with is_developer=True.
    """
    def allow_request(self, request, view):
        if request.user and hasattr(request.user, 'is_developer') and request.user.is_developer:
            return True
        return super().allow_request(request, view)


class BurstRateThrottle(DeveloperBypassMixin, UserRateThrottle):
    """
    Throttle for burst requests (short-term rate limiting).
    Used for endpoints that should have strict limits.
    """
    scope = 'burst'


class SustainedRateThrottle(DeveloperBypassMixin, UserRateThrottle):
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


class ProUserRateThrottle(DeveloperBypassMixin, UserRateThrottle):
    """
    Higher rate limits for PRO users.
    """
    scope = 'pro_user'


class LoginRateThrottle(AnonRateThrottle):
    """
    Strict rate limiting for login endpoints to prevent brute force attacks.
    """
    scope = 'login'


class RegistrationRateThrottle(AnonRateThrottle):
    """
    Rate limiting for registration endpoints.
    """
    scope = 'registration'


class CheckDateRateThrottle(DeveloperBypassMixin, UserRateThrottle):
    """
    Rate limiting for check-date / check previous workout endpoints.
    Prevents abuse when polling or scanning many dates.
    """
    scope = 'check_date'
