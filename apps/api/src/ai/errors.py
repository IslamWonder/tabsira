"""
Errors of a model call.

Every failure carries a stable code, recorded with the call and used to decide
whether another attempt may help. The message is for logs: it never holds the
request, the image or a key.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ai.records import CallRecord


class AiErrorCode(StrEnum):
    """Why a model call failed. A code is never renamed or reused."""

    TIMEOUT = "timeout"
    NETWORK = "network"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    BAD_REQUEST = "bad_request"
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    REFUSED = "refused"
    TRUNCATED = "truncated"
    INVALID_OUTPUT = "invalid_output"
    NOT_CONFIGURED = "not_configured"
    NOT_SUPPORTED = "not_supported"
    FORBIDDEN_MODEL = "forbidden_model"


# Failures another attempt can fix: the provider was slow, busy or broken for a
# moment, or the model wrote an answer that does not match the schema.
RETRYABLE = frozenset(
    {
        AiErrorCode.TIMEOUT,
        AiErrorCode.NETWORK,
        AiErrorCode.RATE_LIMITED,
        AiErrorCode.SERVER_ERROR,
        AiErrorCode.INVALID_OUTPUT,
    }
)


class AiCallError(Exception):
    """A model call failed; `record` describes the call when one was made."""

    def __init__(
        self,
        code: AiErrorCode,
        message: str,
        *,
        record: CallRecord | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.record = record
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE
