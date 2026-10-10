"""Thin synchronous service-to-service HTTP client with retries and request-id propagation."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .errors import NotFoundError, UpstreamServiceError
from .logging import request_id_ctx
from .middleware import REQUEST_ID_HEADER

log = logging.getLogger(__name__)


class ServiceClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        timeout: float = 10.0,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.retries = retries
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)

    def _headers(self) -> dict[str, str]:
        h = {}
        if rid := request_id_ctx.get():
            h[REQUEST_ID_HEADER] = rid
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self._client.request(method, path, headers=self._headers(), **kwargs)
                if resp.status_code == 404:
                    raise NotFoundError(f"{self.base_url}{path} not found")
                if resp.status_code >= 500:
                    raise UpstreamServiceError(f"{self.base_url}{path} returned {resp.status_code}")
                resp.raise_for_status()
                return resp.json() if resp.content else None
            except (httpx.TransportError, UpstreamServiceError) as exc:
                last_exc = exc
                log.warning("upstream_retry", extra={"url": f"{self.base_url}{path}", "attempt": attempt})
                time.sleep(min(0.25 * 2**attempt, 2.0))
        raise UpstreamServiceError(f"{self.base_url}{path} unavailable: {last_exc}")

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)
