"""Domain errors raised by services and translated to HTTP responses in one place (`install_error_handlers`).

Services stay free of FastAPI: they raise these, and the API layer decides the status code. The response body keeps the
`{"detail": "..."}` shape FastAPI uses for its own errors, so clients handle every failure the same way.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class: `message` is shown to the user (Vietnamese), `status_code` is the HTTP status."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(AppError):
    """The resource does not exist, or the caller may not know that it does (the two are deliberately indistinguishable)."""

    status_code = 404


class Forbidden(AppError):
    """The caller is authenticated but not allowed to do this."""

    status_code = 403


class Conflict(AppError):
    """The request clashes with existing state (duplicate name, duplicate document)."""

    status_code = 409


class DuplicateDocument(Conflict):
    """The same file is already in the store (for the same unit); `document_id` points at it."""

    def __init__(self, message: str, document_id: int):
        super().__init__(message)
        self.document_id = document_id


class ValidationFailed(AppError):
    """A submitted value is invalid; the message says which and why."""

    status_code = 422


class ContentBlocked(ValidationFailed):
    """The message was refused by the input screening; the text explains why and says that the attempt was recorded."""


class Unauthorized(AppError):
    """Missing, invalid or expired credentials."""

    status_code = 401


class PayloadTooLarge(AppError):
    """An upload exceeds the configured limit."""

    status_code = 413


class ServiceUnavailable(AppError):
    """A dependency (search index, model server) is unreachable; the request can be retried later."""

    status_code = 503


class ExternalEndpointNotConfirmed(AppError):
    """A model endpoint outside the private network was submitted without the administrator's confirmation."""

    status_code = 409

    def __init__(self, message: str, hosts: list[str]):
        super().__init__(message)
        self.hosts = hosts


def install_error_handlers(app: FastAPI) -> None:
    """Registers the handlers that turn `AppError` into JSON responses."""

    @app.exception_handler(ExternalEndpointNotConfirmed)
    async def _external(_: Request, exc: ExternalEndpointNotConfirmed) -> JSONResponse:
        return JSONResponse({"detail": exc.message, "code": "external_endpoint", "hosts": exc.hosts}, status_code=exc.status_code)

    @app.exception_handler(ContentBlocked)
    async def _blocked(_: Request, exc: ContentBlocked) -> JSONResponse:
        return JSONResponse({"detail": exc.message, "code": "moderation"}, status_code=exc.status_code)

    @app.exception_handler(DuplicateDocument)
    async def _duplicate(_: Request, exc: DuplicateDocument) -> JSONResponse:
        return JSONResponse({"detail": exc.message, "code": "duplicate", "document_id": exc.document_id}, status_code=exc.status_code)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)
