"""
Where the browser sends its errors.

The web app carries no GlitchTip DSN: a key in a client bundle is a key anyone can
spam, and the visitor's browser must make no third-party request. Pages post here
instead, and the API cleans everything (`src/error_tracking.py`) before forwarding.

No sign-in is needed: an error can happen before there is one, on the sign-in page
itself. The bounds are the schema, the body size cap (`BodyLimitMiddleware`, set in
`main`) and a per-address and a global rate limit. With no DSN configured the
answer is 204 and the report is dropped, so a stale tab never errors on its own
error report.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from src.deps import IpHashDep, SettingsDep
from src.error_tracking import WebReporter
from src.errors import AppError, ErrorCode
from src.schemas.client_errors import ClientReportBatch
from src.services.window_limiter import WindowLimiter

router = APIRouter(prefix="/client-errors", tags=["client-errors"])

# The largest body the route reads. Ten reports at their schema maximum are about
# 190 KB; a real page sends a few hundred bytes.
MAX_BODY_BYTES = 256 * 1024
# Per address, in each worker.
ADDRESS_LIMIT = 60
# Over every address, in each worker: a flood of fresh addresses still stops here.
GLOBAL_LIMIT = 600
WINDOW_SECONDS = 300


class ClientErrorLimits:
    """The two limiters of the route, one set per application."""

    def __init__(self) -> None:
        self.per_address = WindowLimiter(ADDRESS_LIMIT, WINDOW_SECONDS)
        self.overall = WindowLimiter(GLOBAL_LIMIT, WINDOW_SECONDS, max_keys=1)


def get_limits(request: Request) -> ClientErrorLimits:
    """Return the application's limiters, built on first use."""
    limits: ClientErrorLimits | None = getattr(request.app.state, "client_error_limits", None)
    if limits is None:
        limits = ClientErrorLimits()
        request.app.state.client_error_limits = limits
    return limits


def get_reporter(request: Request, settings: SettingsDep) -> WebReporter:
    """Return the application's forwarder to GlitchTip, built on first use."""
    reporter: WebReporter | None = getattr(request.app.state, "web_reporter", None)
    if reporter is None:
        reporter = WebReporter(settings, request.app.version)
        request.app.state.web_reporter = reporter
    return reporter


ReporterDep = Annotated[WebReporter, Depends(get_reporter)]


def enforce_limits(
    limits: Annotated[ClientErrorLimits, Depends(get_limits)], ip_hash: IpHashDep
) -> None:
    """Answer 429 when this address, or this worker as a whole, has sent too many reports."""
    retry_after = limits.per_address.hit(ip_hash)
    if retry_after is None:
        retry_after = limits.overall.hit("all")
    if retry_after is not None:
        raise AppError(
            ErrorCode.RATE_LIMITED,
            "Too many error reports. Try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(max(int(retry_after), 1))},
        )


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_limits)],
    summary="Report errors a page saw",
)
async def report_client_errors(
    batch: ClientReportBatch, request: Request, reporter: ReporterDep
) -> Response:
    """
    Accept a page's error reports and forward them to GlitchTip, cleaned.

    Answers 204 whether or not anything is forwarded.
    """
    if reporter.enabled:
        reporter.report(
            batch.items,
            request_id=getattr(request.state, "request_id", None),
            user_agent=request.headers.get("user-agent"),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
