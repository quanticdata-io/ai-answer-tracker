"""Minimal client for the one QuanticData endpoint this tool calls.

``POST /scraper/ai-visibility`` (https://quanticdata.io/docs/) audits a page and, when
``queries`` is given, asks AI engines the questions and reports per (query x engine)
whether the page's domain is cited or the brand is mentioned.

Every answer uses the envelope ``{"type": "response"|"error", "message": ..., "payload": ...}``.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from ._version import __version__

DEFAULT_BASE_URL = "https://api.quanticdata.io/v1"
ENV_API_KEY = "QUANTICDATA_API_KEY"
ENV_API_BASE = "QUANTICDATA_API_BASE"
AI_VISIBILITY_PATH = "/scraper/ai-visibility"


class QuanticDataError(Exception):
    """The API answered with an error, or could not be reached."""

    def __init__(self, message: str, *, status: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload


class AuthenticationError(QuanticDataError):
    """HTTP 401: missing, unknown, disabled or expired API key."""


class PaymentRequiredError(QuanticDataError):
    """HTTP 402: the free tier and the balance cannot cover the call, or the spend cap is reached."""


class RateLimitError(QuanticDataError):
    """HTTP 429. ``retry_after`` is in seconds when the server sent it."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        payload: Any = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status=status, payload=payload)
        self.retry_after = retry_after


def _retry_after(response: httpx.Response) -> float | None:
    header = response.headers.get("retry-after")
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            return None
    return None


class QuanticDataClient:
    """Sends audit requests with ``Authorization: Bearer <key>``.

    A 429 is retried after ``Retry-After`` when the wait is short. A request that
    reached the server is never sent again after a 5xx or a timeout, so a billed
    call is never repeated by this client.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 300.0,
        max_retries: int = 2,
        max_retry_wait: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        key = api_key or os.environ.get(ENV_API_KEY, "").strip()
        if not key:
            raise AuthenticationError(
                f"No API key: pass api_key or set {ENV_API_KEY}. "
                "Create one on the API keys page of the QuanticData dashboard."
            )
        self.base_url = (base_url or os.environ.get(ENV_API_BASE) or DEFAULT_BASE_URL).rstrip("/")
        self.max_retries = max_retries
        self.max_retry_wait = max_retry_wait
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {key}",
                "User-Agent": f"ai-answer-tracker/{__version__}",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> QuanticDataClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def ai_visibility(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Runs one audit and returns the ``payload`` of the answer."""
        attempt = 0
        while True:
            try:
                response = self._http.post(AI_VISIBILITY_PATH, json=dict(body))
            except httpx.ConnectError as exc:
                # The request never reached the server: safe to retry.
                if attempt < self.max_retries:
                    attempt += 1
                    self._sleep(2.0 * attempt)
                    continue
                raise QuanticDataError(f"Cannot reach {self.base_url}: {exc}") from exc
            except httpx.HTTPError as exc:
                raise QuanticDataError(f"Request to {self.base_url} failed: {exc}") from exc

            try:
                data: Any = response.json()
            except ValueError:
                data = None
            message = data.get("message") if isinstance(data, Mapping) else None
            payload = data.get("payload") if isinstance(data, Mapping) else None
            text = str(message or response.reason_phrase or "error")

            if response.status_code == 429:
                wait = _retry_after(response)
                if attempt < self.max_retries and wait is not None and wait <= self.max_retry_wait:
                    attempt += 1
                    self._sleep(wait)
                    continue
                raise RateLimitError(text, status=429, payload=payload, retry_after=wait)
            if response.status_code == 401:
                raise AuthenticationError(text, status=401, payload=payload)
            if response.status_code == 402:
                raise PaymentRequiredError(text, status=402, payload=payload)
            if response.status_code >= 400:
                raise QuanticDataError(f"HTTP {response.status_code}: {text}", status=response.status_code)
            if not isinstance(payload, dict):
                raise QuanticDataError("The answer has no payload object", status=response.status_code)
            return payload
