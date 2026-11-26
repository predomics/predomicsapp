"""Rate limiting setup using slowapi."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings


def _get_user_or_ip(request):
    """Rate limit key: user ID from a *valid* JWT, else the client IP address.

    Unverified header values (such as an arbitrary X-API-Key) must never choose
    the bucket: a caller could rotate them to get a fresh allowance per request.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        from .security import decode_access_token

        user_id = decode_access_token(auth[7:])
        if user_id:
            return user_id
    return get_remote_address(request)


def get_ip(request):
    """Rate limit key for unauthenticated endpoints (login, register, reset): IP only."""
    return get_remote_address(request)


limiter = Limiter(
    key_func=_get_user_or_ip,
    default_limits=[settings.rate_limit_api] if settings.rate_limit_enabled else [],
    enabled=settings.rate_limit_enabled,
)
