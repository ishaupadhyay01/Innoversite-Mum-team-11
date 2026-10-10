"""Optional static bearer-token auth (PDF advanced task: "basic authentication").

If ``settings.api_token`` is empty, auth is disabled. Health endpoints are never protected.
Replace with OAuth2/OIDC (e.g. bank SSO) behind the gateway for production.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable

from fastapi import Request

from .errors import UnauthorizedError


def bearer_guard(get_token: Callable[[], str]) -> Callable[[Request], None]:
    def _guard(request: Request) -> None:
        expected = get_token()
        if not expected:
            return
        header = request.headers.get("Authorization", "")
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(supplied, expected):
            raise UnauthorizedError("Missing or invalid bearer token")

    return _guard
