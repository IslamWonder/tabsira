"""A GlitchTip transport that keeps what it is given, for the tests that read what would be sent."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from src import error_tracking


class Recorder:
    """A transport that keeps what it is given, so a test can read what would have been sent."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def transport(self) -> type[Transport]:
        recorder = self

        class Capture(Transport):
            def capture_envelope(self, envelope: Any) -> None:
                recorder.events.extend(
                    item.payload.json for item in envelope.items if item.type == "event"
                )

            def flush(self, timeout: float, callback: Callable[..., Any] | None = None) -> None:
                return None

        return Capture


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Iterator[Recorder]:
    """Swap the SDK's transport for one that records, and leave the SDK off afterwards."""
    record = Recorder()
    monkeypatch.setattr(error_tracking, "ShortTimeoutTransport", record.transport())
    monkeypatch.setattr(error_tracking, "_initialised", False)
    yield record
    sentry_sdk.get_client().close(timeout=0)
    # Detach the client rather than call `init` again: a bare `init` would leave the
    # process with the SDK's default options, which read the body of a failed
    # multipart request and leave its temporary file open for every later test.
    sentry_sdk.get_global_scope().set_client(None)
