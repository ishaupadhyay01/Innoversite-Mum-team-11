"""Uniform error model.

Every error response from every service has the same envelope::

    {"error": {"code": "DUPLICATE_DOCUMENT", "message": "...", "details": {...}, "request_id": "..."}}

Raise an :class:`IrisError` subclass from business code; never build HTTP errors by hand.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging import request_id_ctx

log = logging.getLogger(__name__)


class IrisError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}


class NotFoundError(IrisError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(IrisError):
    status_code = 409
    code = "CONFLICT"


class ValidationFailedError(IrisError):
    status_code = 422
    code = "VALIDATION_FAILED"


class PayloadTooLargeError(IrisError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"


class UnauthorizedError(IrisError):
    status_code = 401
    code = "UNAUTHORIZED"


class FeatureDisabledError(IrisError):
    status_code = 501
    code = "FEATURE_DISABLED"


class UpstreamServiceError(IrisError):
    status_code = 502
    code = "UPSTREAM_ERROR"


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}, "request_id": request_id_ctx.get()}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(IrisError)
    async def _iris(_: Request, exc: IrisError) -> JSONResponse:
        if exc.status_code >= 500:
            log.error("iris_error", extra={"code": exc.code, "detail": exc.message})
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            error_body("REQUEST_VALIDATION_FAILED", "Request is invalid", {"errors": exc.errors()}),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(error_body(f"HTTP_{exc.status_code}", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error")
        return JSONResponse(error_body("INTERNAL_ERROR", "An unexpected error occurred"), status_code=500)
