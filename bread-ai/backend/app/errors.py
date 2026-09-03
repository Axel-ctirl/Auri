"""Structured error types and FastAPI exception handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class BreadError(Exception):
    """Base class for errors Bread reports to the client on purpose."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "bread_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.hint = hint
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        if self.details:
            payload["details"] = self.details
        return {"error": payload}


class NotFoundError(BreadError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ValidationFailedError(BreadError):
    status_code = 422
    code = "validation_failed"


class ConflictError(BreadError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class UnauthorizedError(BreadError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class RateLimitedError(BreadError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class PayloadTooLargeError(BreadError):
    status_code = 413
    code = "payload_too_large"


class ModelNotLoadedError(BreadError):
    status_code = status.HTTP_409_CONFLICT
    code = "model_not_loaded"


class BackendUnavailableError(BreadError):
    """A required optional dependency, driver or model file is missing."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "backend_unavailable"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BreadError)
    async def _handle_bread_error(_: Request, exc: BreadError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": f"http_{exc.status_code}", "message": detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": "The request body did not match the expected schema.",
                    "details": {"errors": exc.errors()},
                }
            },
        )
