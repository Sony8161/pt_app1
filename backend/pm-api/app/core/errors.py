"""
Consistent API error envelope.

Every error response has the shape::

    {"error": {"code": "not_found", "message": "Project not found", "details": []}}

``details`` carries field-level validation messages when relevant.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Base class for errors that map directly to an HTTP response."""

    status_code = 500
    code = "internal_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or "An unexpected error occurred"
        if code:
            self.code = code
        self.details = details or []
        self.headers = headers or {}

    def to_payload(self) -> dict[str, Any]:
        """Serialisable error envelope."""
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class ValidationError(ApiError):
    """Request failed business validation (400)."""

    status_code = 400
    code = "validation_error"


class AuthError(ApiError):
    """Missing, invalid or expired credentials (401)."""

    status_code = 401
    code = "unauthenticated"

    def __init__(self, message: str = "Authentication required", **kwargs: Any) -> None:
        kwargs.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(message, **kwargs)


class ForbiddenError(ApiError):
    """Authenticated but not allowed (403)."""

    status_code = 403
    code = "forbidden"

    def __init__(self, message: str = "You do not have permission to perform this action", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class NotFoundError(ApiError):
    """Resource does not exist or is not visible to the caller (404)."""

    status_code = 404
    code = "not_found"


class ConflictError(ApiError):
    """Request conflicts with current state, e.g. duplicate name (409)."""

    status_code = 409
    code = "conflict"


def _envelope(status_code: int, code: str, message: str, details: list[dict[str, Any]] | None = None,
              headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or []}},
        headers=headers,
    )


def _validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    details = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ()) if part not in ("body",)]
        details.append({"field": ".".join(loc) or "body", "message": err.get("msg", "Invalid value")})
    return details


def register_error_handlers(app: FastAPI) -> None:
    """Attach handlers so every failure path uses the same envelope."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload(), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(400, "validation_error", "Request validation failed", _validation_details(exc))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
        headers = dict(exc.headers) if exc.headers else None
        return _envelope(exc.status_code, code.get(exc.status_code, "http_error"), str(exc.detail), headers=headers)

    @app.exception_handler(psycopg.errors.UniqueViolation)
    async def handle_unique_violation(_: Request, exc: psycopg.errors.UniqueViolation) -> JSONResponse:
        # Safety net for races the services' own duplicate checks cannot see.
        logger.warning("Unique violation: %s", exc)
        return _envelope(409, "conflict", "That value is already in use.")

    @app.exception_handler(psycopg.OperationalError)
    async def handle_db_unavailable(_: Request, exc: psycopg.OperationalError) -> JSONResponse:
        from app.db import reset_connection  # local import avoids a circular dependency

        logger.error("Database unavailable: %s", exc)
        reset_connection()
        return _envelope(503, "database_unavailable", "The database is temporarily unavailable. Please retry.")

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return _envelope(500, "internal_error", "An unexpected error occurred")
