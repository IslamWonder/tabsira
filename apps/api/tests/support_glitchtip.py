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


def leave_sdk_off() -> None:
    """
    Close the SDK and start a bare one with no integration and no DSN.

    A plain `init` would switch the FastAPI and Starlette integrations on for every later
    test, and they read each request body: a multipart upload was parsed a second time and
    its temporary file never closed, surfacing as an unclosed-file warning in a later test.
    """
    sentry_sdk.get_client().close(timeout=0)
    # A named release: without one the SDK runs `git` to find it.
    sentry_sdk.init(release="test", default_integrations=False, auto_enabling_integrations=False)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Iterator[Recorder]:
    """Swap the SDK's transport for one that records, and leave the SDK off afterwards."""
    record = Recorder()
    monkeypatch.setattr(error_tracking, "ShortTimeoutTransport", record.transport())
    monkeypatch.setattr(error_tracking, "_initialised", False)
    yield record
    leave_sdk_off()
