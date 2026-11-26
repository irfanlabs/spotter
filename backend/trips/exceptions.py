"""Domain exceptions and the DRF exception handler that renders them.

Every error leaves the API in one shape:

    {"error": {"code": "UPSTREAM_TIMEOUT", "message": "...", "details": {...}}}
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class SpotterError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "INTERNAL_ERROR"
    default_detail = "Something went wrong on our side. Please try again."

    def __init__(self, message: str | None = None, *, details: dict | None = None):
        super().__init__(detail=message or self.default_detail)
        self.details = details or {}


class PlaceNotFound(SpotterError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "PLACE_NOT_FOUND"
    default_detail = "We couldn't find that location."


class NoRouteFound(SpotterError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "NO_ROUTE"
    default_detail = "No drivable route exists between those two locations."


class ForecastOutOfRange(SpotterError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "FORECAST_OUT_OF_RANGE"
    default_detail = "The trip extends beyond the available weather forecast."


class UpstreamError(SpotterError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "UPSTREAM_ERROR"
    default_detail = "A data provider returned an unexpected response."


class UpstreamTimeout(UpstreamError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "UPSTREAM_TIMEOUT"
    default_detail = "A data provider took too long to respond. Please try again."


class UpstreamRateLimited(UpstreamError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "UPSTREAM_RATE_LIMITED"
    default_detail = "A data provider is rate limiting us. Please retry in a minute."


def _flatten(detail):
    """Turn DRF's nested ValidationError detail into {field: [messages]}."""
    if isinstance(detail, dict):
        return {k: _flatten(v) for k, v in detail.items()}
    if isinstance(detail, list):
        return [str(x) if not isinstance(x, (dict, list)) else _flatten(x) for x in detail]
    return str(detail)


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        # Anything unexpected: log with traceback, never leak internals.
        logger.exception("Unhandled error in %s", context.get("view"))
        return Response(
            {"error": {"code": "INTERNAL_ERROR", "message": SpotterError.default_detail, "details": {}}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, SpotterError):
        code, message, details = exc.code, str(exc.detail), exc.details
    elif isinstance(exc, ValidationError):
        code, message, details = "VALIDATION_ERROR", "Please check the highlighted fields.", {"fields": _flatten(exc.detail)}
    else:
        code = getattr(exc, "default_code", "error").upper()
        message = str(getattr(exc, "detail", "Request failed."))
        details = {}
        if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            code, message = "RATE_LIMITED", "Too many requests. Please slow down and try again shortly."

    if response.status_code >= 500:
        logger.warning("API error %s: %s", code, message)
    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
