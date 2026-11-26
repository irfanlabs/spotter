"""Shared HTTP session for upstream providers: timeouts, retries, error mapping."""

from __future__ import annotations

import logging
from functools import lru_cache

import requests
import urllib3
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..exceptions import UpstreamError, UpstreamRateLimited, UpstreamTimeout

logger = logging.getLogger(__name__)


def _is_timeout(exc: BaseException) -> bool:
    """requests wraps urllib3 read timeouts in ConnectionError once retries are spent."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, (requests.Timeout, urllib3.exceptions.TimeoutError)) or "timed out" in str(exc).lower():
            return True
        exc = exc.__cause__ or exc.__context__ or (exc.args[0] if exc.args and isinstance(exc.args[0], BaseException) else None)
    return False


@lru_cache(maxsize=1)
def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        read=1,  # a second slow read is enough; more would outlast the browser's patience
        backoff_factor=0.6,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": settings.UPSTREAM_USER_AGENT, "Accept": "application/json"})
    return s


def get_json(url: str, *, provider: str, timeout: float, params: dict | None = None, ok_statuses=(200,)) -> dict | list:
    """GET JSON and translate every failure mode into a SpotterError."""
    try:
        resp = session().get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        if _is_timeout(exc):
            logger.warning("%s timed out: %s", provider, url)
            raise UpstreamTimeout(f"{provider} took too long to respond. Please try again.") from exc
        logger.warning("%s unreachable: %s", provider, exc)
        raise UpstreamError(f"{provider} is currently unreachable. Please try again shortly.") from exc

    if resp.status_code == 429:
        raise UpstreamRateLimited(f"{provider} is rate limiting requests. Please retry in a minute.")
    if resp.status_code not in ok_statuses:
        logger.warning("%s returned HTTP %s: %.200s", provider, resp.status_code, resp.text)
        raise UpstreamError(f"{provider} returned an error (HTTP {resp.status_code}).", details={"provider": provider})
    try:
        return resp.json()
    except ValueError as exc:
        raise UpstreamError(f"{provider} returned an unreadable response.") from exc
