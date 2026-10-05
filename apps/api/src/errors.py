"""
Error responses.

Every error the API returns has the same body, `{"error": CODE, "detail": text}`.
The code is stable: clients branch on it and the web app maps it to an Arabic
message. The detail is for developers and logs.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from src.middleware.request_id import REQUEST_ID_HEADER
from src.responses import OrjsonResponse

log = logging.getLogger("tabsira.errors")


class ErrorCode(StrEnum):
    """The stable error codes. A code is never renamed or reused."""

    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    HTTP_ERROR = "HTTP_ERROR"
    # Accounts
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    EMAIL_TAKEN = "EMAIL_TAKEN"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
    INVALID_TOKEN = "INVALID_TOKEN"  # noqa: S105 - an error code, not a password  # nosec B105
    ORIGIN_NOT_ALLOWED = "ORIGIN_NOT_ALLOWED"
    CONSENT_NOT_ALLOWED = "CONSENT_NOT_ALLOWED"
    GOOGLE_NOT_CONFIGURED = "GOOGLE_NOT_CONFIGURED"
    # The social network
    HANDLE_TAKEN = "HANDLE_TAKEN"
    PUBLIC_IDENTITY_REQUIRED = "PUBLIC_IDENTITY_REQUIRED"
    INSIGHT_NOT_PUBLISHABLE = "INSIGHT_NOT_PUBLISHABLE"
    # The account declared it is under 13: nothing of its own is made public (v2 §5).
    UNDER_13_CANNOT_PUBLISH = "UNDER_13_CANNOT_PUBLISH"
    INVALID_CURSOR = "INVALID_CURSOR"
    GONE = "GONE"
    # The codes below are lower case on purpose: they are the strings the web app matches.
    legal_acceptance_required = "legal_acceptance_required"
    mail_unavailable = "mail_unavailable"
    # Decision 64, HTTP 403: a guest who holds one scan of its own must sign up; an account
    # whose profile is not completed must complete it. The web app matches the strings.
    account_required = "account_required"
    profile_required = "profile_required"
    # The bot check (Cloudflare Turnstile, decision 56) was missing or refused: HTTP 403.
    turnstile_failed = "turnstile_failed"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    # The scan workflow: the codes of master prompt v2 §26, then the ones it needs besides.
    ASSET_MISSING = "ASSET_MISSING"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    VISION_FAILED = "VISION_FAILED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NO_RELEVANT_EVIDENCE = "NO_RELEVANT_EVIDENCE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    # The store answered but holds no searchable corpus (no vectors of the configured model).
    CORPUS_UNAVAILABLE = "CORPUS_UNAVAILABLE"
    # A search step failed (the query embedding), so the search was not run.
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
    PAIR_INCOMPLETE = "PAIR_INCOMPLETE"
    CHAT_LIMIT_REACHED = "CHAT_LIMIT_REACHED"
    CHAT_CLOSED = "CHAT_CLOSED"
    SAVE_FAILED = "SAVE_FAILED"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    IMAGE_EMPTY = "IMAGE_EMPTY"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    IMAGE_TOO_SMALL = "IMAGE_TOO_SMALL"
    IMAGE_UNSUPPORTED = "IMAGE_UNSUPPORTED"
    IMAGE_INVALID = "IMAGE_INVALID"
    # The address of a photo is refused before any request (not http(s), a port, a private address).
    IMAGE_URL_REFUSED = "IMAGE_URL_REFUSED"
    # The photo at an accepted address could not be fetched (time, status, type, size).
    IMAGE_FETCH_FAILED = "IMAGE_FETCH_FAILED"
    QUEUE_UNAVAILABLE = "QUEUE_UNAVAILABLE"
    SCAN_BUSY = "SCAN_BUSY"
    SCAN_TIMEOUT = "SCAN_TIMEOUT"
    CHAT_IN_PROGRESS = "CHAT_IN_PROGRESS"
    CHAT_ANSWER_REJECTED = "CHAT_ANSWER_REJECTED"
    TREASURE_NOT_READY = "TREASURE_NOT_READY"


_CODE_BY_STATUS: dict[int, ErrorCode] = {
    HTTPStatus.BAD_REQUEST: ErrorCode.BAD_REQUEST,
    HTTPStatus.UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    HTTPStatus.FORBIDDEN: ErrorCode.FORBIDDEN,
    HTTPStatus.NOT_FOUND: ErrorCode.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    HTTPStatus.CONFLICT: ErrorCode.CONFLICT,
    HTTPStatus.GONE: ErrorCode.GONE,
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: ErrorCode.PAYLOAD_TOO_LARGE,
    HTTPStatus.UNPROCESSABLE_ENTITY: ErrorCode.VALIDATION_ERROR,
    HTTPStatus.TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
    HTTPStatus.INTERNAL_SERVER_ERROR: ErrorCode.INTERNAL_ERROR,
    HTTPStatus.SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
}


class FieldError(BaseModel):
    """One rejected field of a request: where it is and why it was refused."""

    loc: list[str | int]
    message: str
    type: str


class ErrorResponse(BaseModel):
    """The body of every error response."""

    error: ErrorCode
    detail: str
    # Only on VALIDATION_ERROR: the fields that were refused.
    fields: list[FieldError] | None = None
    # Only on legal_acceptance_required: the versions to accept, so the page need not ask twice.
    terms_version: str | None = None
    privacy_version: str | None = None


class AppError(Exception):
    """An error a route raises on purpose, with its HTTP status and stable code."""

    def __init__(
        self,
        code: ErrorCode,
        detail: str,
        *,
        status_code: int = HTTPStatus.BAD_REQUEST,
        headers: dict[str, str] | None = None,
        extra: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = int(status_code)
        self.headers = headers
        # Further top-level fields of the error body (see `ErrorResponse`).
        self.extra = extra or {}


def error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    detail: str,
    *,
    headers: Mapping[str, str] | None = None,
    fields: list[FieldError] | None = None,
    extra: Mapping[str, str] | None = None,
) -> Response:
    """Build the JSON error response, carrying the request id when there is one."""
    response_headers = dict(headers or {})
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        response_headers[REQUEST_ID_HEADER] = request_id
    body = ErrorResponse.model_validate(
        {"error": code, "detail": detail, "fields": fields, **(extra or {})}
    )
    return OrjsonResponse(
        body.model_dump(mode="json", exclude_none=True),
        status_code=status_code,
        headers=response_headers,
    )


def _expect[E: Exception](exc: Exception, kind: type[E]) -> E:
    """
    Return `exc` as a `kind`, or raise when a handler was registered for the wrong one.

    Starlette types every handler's exception as `Exception`; this narrows it
    with a check that still runs under `python -O`, unlike an `assert`.
    """
    if not isinstance(exc, kind):
        message = f"{type(exc).__name__} was routed to the handler of {kind.__name__}"
        raise TypeError(message)
    return exc


async def handle_app_error(request: Request, exc: Exception) -> Response:
    """Answer a deliberate `AppError`."""
    error = _expect(exc, AppError)
    return error_response(
        request,
        error.status_code,
        error.code,
        error.detail,
        headers=error.headers,
        extra=error.extra,
    )


async def handle_http_exception(request: Request, exc: Exception) -> Response:
    """Answer an `HTTPException`, such as the 404 of an unknown path."""
    error = _expect(exc, StarletteHTTPException)
    code = _CODE_BY_STATUS.get(error.status_code, ErrorCode.HTTP_ERROR)
    return error_response(
        request, error.status_code, code, str(error.detail), headers=error.headers
    )


async def handle_validation_error(request: Request, exc: Exception) -> Response:
    """
    Answer a request that does not match its schema.

    The fields are listed by location and reason only. The rejected values are
    left out: they can hold a password or a private note.
    """
    error = _expect(exc, RequestValidationError)
    fields = [
        FieldError(loc=list(item["loc"]), message=item["msg"], type=item["type"])
        for item in error.errors()
    ]
    return error_response(
        request,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        ErrorCode.VALIDATION_ERROR,
        "The request does not match the expected format.",
        fields=fields,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> Response:
    """Answer any other failure with a 500 that reveals nothing about it."""
    log.error(
        "unhandled error on %s %s (request %s)",
        request.method,
        request.url.path,
        getattr(request.state, "request_id", "-"),
        exc_info=exc,
    )
    return error_response(
        request,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL_ERROR,
        "Internal server error.",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install the handlers that give every error the same JSON body."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
