"""Shared HTTP helpers with retry and Retry-After handling for Deadlock APIs."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def build_headers(api_key: str | None = None) -> dict[str, str]:
    """Build standard request headers, optionally attaching X-API-Key."""
    headers = {"Accept": "application/json", "User-Agent": "deadlock-counterbuild-bot/1.0"}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _parse_retry_after(header_value: str | None, fallback_s: float) -> float:
    if not header_value:
        return fallback_s
    try:
        return max(float(header_value), 0.5)
    except ValueError:
        return fallback_s


def get_with_retries(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_s: float = 30.0,
    max_retries: int = 5,
    base_backoff_s: float = 1.5,
) -> requests.Response:
    """Perform an HTTP GET with backoff and Retry-After support on 429/503/5xx."""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = session.get(url, params=params, headers=headers, timeout=timeout_s)
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            wait_s = base_backoff_s * (2**attempt)
            logger.warning("Request error (%s), retrying in %.1fs...", exc, wait_s)
            time.sleep(wait_s)
            continue

        if response.status_code not in RETRYABLE_STATUS_CODES:
            response.raise_for_status()
            return response

        if attempt >= max_retries:
            response.raise_for_status()

        fallback_s = base_backoff_s * (2**attempt)
        wait_s = _parse_retry_after(response.headers.get("Retry-After"), fallback_s)
        logger.warning(
            "Received HTTP %s from %s; waiting %.1fs (attempt %d/%d)",
            response.status_code,
            url,
            wait_s,
            attempt + 1,
            max_retries,
        )
        time.sleep(wait_s)

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Exhausted retries requesting {url}")
