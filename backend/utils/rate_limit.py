"""Shared rate-limiting utility.

Provides a ``rate_limit`` decorator that wraps slowapi when available
and degrades to a no-op when the package is not installed.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
    _HAS_SLOWAPI = True
except ImportError:
    _HAS_SLOWAPI = False
    limiter = None  # type: ignore[assignment]


def rate_limit(limit_string: str):
    """Return a rate-limit dependency; no-op when slowapi is unavailable."""
    if _HAS_SLOWAPI and limiter is not None:
        return limiter.limit(limit_string)

    def _noop(func):
        return func

    return _noop
