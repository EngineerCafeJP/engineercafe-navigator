"""Tests for rate_limit utility (#120)"""

from unittest.mock import MagicMock

from backend.utils.rate_limit import _HAS_SLOWAPI, rate_limit


def test_rate_limit_returns_callable():
    """rate_limit should return a decorator (callable)"""
    decorator = rate_limit("10/minute")
    assert callable(decorator)


def test_rate_limit_preserves_function():
    """Decorator should preserve function (no-op when slowapi absent, wraps when present)"""

    # slowapi requires a `request` parameter on decorated functions,
    # so we always include one for compatibility.
    @rate_limit("10/minute")
    def dummy(request=None):
        return "ok"

    if _HAS_SLOWAPI:
        # When slowapi is installed, the decorator wraps the function
        # but it should remain callable
        assert callable(dummy)
    else:
        # When slowapi is not installed, decorator is a no-op
        assert dummy() == "ok"


def test_rate_limit_different_limits():
    """Different rate limit strings should all return valid decorators"""
    for limit_str in ["60/minute", "30/minute", "10/minute", "5/minute"]:
        decorator = rate_limit(limit_str)
        assert callable(decorator)


def test_rate_limit_decorator_with_request():
    """Decorated function with request param should be callable"""

    mock_request = MagicMock()
    mock_request.app = MagicMock()
    mock_request.app.state = MagicMock()

    @rate_limit("10/minute")
    def handler(request):
        return "handled"

    # The function should remain callable regardless of slowapi availability
    assert callable(handler)
