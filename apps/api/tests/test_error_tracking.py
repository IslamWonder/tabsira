"""
Error tracking: nothing without a DSN, and what is sent has been cleaned.

The scrubbing functions are pure and tested one by one. The rest runs the real
Sentry SDK against a transport that keeps the events in a list, so an assertion
is made on exactly what would have left the process.
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Callable
from typing import Any

import pytest
import sentry_sdk

from src import error_tracking
from src.config import Settings
from src.error_tracking import (
    ARABIC_FILTERED,
    FILTERED,
    SCRIPTURE_FILTERED,
    WebReporter,
    is_private_name,
    is_secret_name,
    scrub_event,
    scrub_mapping,
    scrub_text,
    scrub_url,
    scrub_value,
)
from src.main import create_app
from src.schemas.client_errors import ClientBreadcrumb, ClientReport
from tests.helpers import client_for

DSN = "https://public-key@glitchtip.example.com/7"
WEB_DSN = "https://web-key@glitchtip.example.com/8"
BASMALA = "بسم الله الرحمن الرحيم"


# ─── What counts as private ──────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "password",
        "new_password",
        "Authorization",
        "X-Api-Key",
        "api_key",
        "apikey",
        "Cookie",
        "csrf_token",
        "session_id",
        "client_secret",
        "attendeePW",
        "checksum",
        "credentials",
    ],
)
def test_a_secret_is_known_by_its_name(name):
    assert is_secret_name(name)
    assert is_private_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "email",
        "E-Mail",
        "display_name",
        "age_range",
        "religious_background",
        "gender",
        "goals",
        "knowledge_level",
        "photo",
        "image_url",
        "avatar",
        "exif",
        "latitude",
        "lng",
        "location",
        "coordinates",
        "verse_text",
        "hadith",
        "scripture",
        "text",
        "search_term",
        "caption",
    ],
)
def test_what_belongs_to_a_person_is_known_by_its_name(name):
    assert is_private_name(name)
    assert not is_secret_name(name) or name in {"credentials"}


@pytest.mark.parametrize(
    "name",
    [
        "context",
        "content-type",
        "request_id",
        "route",
        "status_code",
        "pwned_count",
        "textual",
        "db.query",
    ],
)
def test_ordinary_names_are_left_alone(name):
    assert not is_private_name(name)


# ─── Text ────────────────────────────────────────────────────────────


def test_a_query_string_goes_whole_wherever_it_is_written():
    assert scrub_text("GET /geo/places?q=tunis&limit=5 failed") == "GET /geo/places failed"
    assert scrub_text("see https://tabsira.me/a?x=1&y=2 now") == "see https://tabsira.me/a now"
    # A question mark that does not start a query is text.
    assert scrub_text("why? because") == "why? because"


def test_the_value_of_a_private_pair_is_masked_and_others_are_kept():
    assert scrub_text("token=abc123 route=/health") == f"token={FILTERED} route=/health"
    assert scrub_text("a email=x@y.z, b") == f"a email={FILTERED} b"
    assert scrub_text('{"password":"x"} pw=1') == '{"password":"x"} pw=[Filtered]'
    # The value ends at a quote or an ampersand, not at the end of the text.
    assert scrub_text("secret=abc&ok=1") == f"secret={FILTERED}&ok=1"
    assert scrub_text("trailing name=") == "trailing name="


def test_arabic_text_is_replaced_whole_runs_at_a_time():
    assert scrub_text(f"verse {BASMALA} end") == f"verse {ARABIC_FILTERED} end"
    assert scrub_text(f"a {BASMALA}، {BASMALA}؟ b") == f"a {ARABIC_FILTERED} b"
    assert scrub_text("one \u0627 two") == f"one {ARABIC_FILTERED} two"
    # Nothing Arabic, nothing changed; and digits and Latin letters survive.
    assert scrub_text("Error 500 in src/main.py") == "Error 500 in src/main.py"
    assert scrub_text("") == ""


def test_a_long_report_with_no_pairs_is_scrubbed_in_linear_time():
    text = "x" * 20_000 + " " + "\u0627 " * 5_000 + "?" * 5_000

    started = time.perf_counter()
    scrub_text(text)

    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://tabsira.me/a/b?x=1#frag", "https://tabsira.me/a/b"),
        ("https://user:pass@tabsira.me:8443/p", "https://tabsira.me:8443/p"),
        ("/relative/path?token=abc", "/relative/path"),
        ("http://[bad/never?x=1", "http://[bad/never"),
        ("https://tabsira.me/u/محمد", f"https://tabsira.me/u/{ARABIC_FILTERED}"),
        ("", ""),
    ],
)
def test_an_address_loses_credentials_query_and_fragment(url, expected):
    assert scrub_url(url) == expected


def test_a_value_is_scrubbed_whatever_its_shape():
    assert scrub_value(f"token=abc {BASMALA}") == f"token={FILTERED} {ARABIC_FILTERED}"
    assert scrub_value(b"\xff\xd8 a photo") == FILTERED
    assert scrub_value(bytearray(b"x")) == FILTERED
    assert scrub_value({"a": ["email=x@y.z", ("n", 1)], "b": {"gender": "man"}}) == {
        "a": [f"email={FILTERED}", ["n", 1]],
        "b": {"gender": FILTERED},
    }
    assert scrub_value({"b"}) == ["b"]
    assert scrub_value(7) == 7
    assert scrub_value(None) is None


def test_a_mapping_masks_the_value_of_a_private_key():
    assert scrub_mapping({"photo": "x", "route": "/a?b=c", "n": 3}) == {
        "photo": FILTERED,
        "route": "/a",
        "n": 3,
    }


# ─── Events ──────────────────────────────────────────────────────────


def a_full_event() -> dict[str, Any]:
    return {
        "message": f"failed token=abc {BASMALA}",
        "transaction": "GET /geo/places",
        "user": {"id": "u1", "email": "a@b.c", "ip_address": "1.2.3.4"},
        "request": {
            "method": "POST",
            "url": "https://api.tabsira.me/profile?email=a@b.c#x",
            "query_string": "email=a@b.c",
            "data": {"religious_background": "muslim"},
            "cookies": {"session": "s"},
            "env": {"REMOTE_ADDR": "1.2.3.4"},
            "headers": {
                "Authorization": "Bearer x",
                "Cookie": "s=1",
                "X-Forwarded-For": "1.2.3.4",
                "User-Agent": "Mozilla/5.0 Firefox/130.0",
                "Content-Type": "application/json",
                "Host": "api.tabsira.me",
            },
        },
        "logentry": {
            "message": "bad %s",
            "formatted": f"bad {BASMALA}",
            "params": [BASMALA, 4],
        },
        "exception": {
            "values": [
                {"type": "ValueError", "value": f"nope password=hunter2 {BASMALA}"},
                "not a dict",
            ]
        },
        "extra": {"age_range": "18_24", "note": "a", "route": "/x?y=z", "keep": 1},
        "tags": {"area": "api", "location": "tunis"},
        "contexts": {"trace": {"trace_id": "abc"}, "device": {"photo": "p"}},
        "breadcrumbs": {
            "values": [
                {"message": f"GET /a?b=c {BASMALA}", "data": {"url": "/a?b=c", "text": "t"}},
                "not a dict",
            ]
        },
        "spans": [
            {"description": "SELECT 1 /*?x=1*/", "data": {"db.query": "q", "body": "b"}},
            "not a dict",
        ],
    }


def test_an_event_is_cleaned_everywhere():
    event = scrub_event(a_full_event())

    assert event["message"] == f"failed token={FILTERED} {ARABIC_FILTERED}"
    assert "user" not in event
    request = event["request"]
    assert request["url"] == "https://api.tabsira.me/profile"
    assert not {"data", "cookies", "env", "query_string"} & set(request)
    # Only the headers that explain a failure, the user agent as its family.
    assert request["headers"] == {
        "User-Agent": "firefox",
        "Content-Type": "application/json",
        "Host": "api.tabsira.me",
    }
    assert event["logentry"] == {
        "message": "bad %s",
        "formatted": f"bad {ARABIC_FILTERED}",
        "params": [ARABIC_FILTERED, 4],
    }
    assert event["exception"]["values"][0]["value"] == f"nope password={FILTERED} {ARABIC_FILTERED}"
    assert event["extra"] == {
        "age_range": FILTERED,
        "note": FILTERED,
        "route": "/x",
        "keep": 1,
    }
    assert event["tags"] == {"area": "api", "location": FILTERED}
    assert event["contexts"] == {"trace": {"trace_id": "abc"}, "device": {"photo": FILTERED}}
    crumb = event["breadcrumbs"]["values"][0]
    assert crumb["message"] == f"GET /a {ARABIC_FILTERED}"
    assert crumb["data"] == {"url": "/a", "text": FILTERED}
    span = event["spans"][0]
    assert span["description"] == "SELECT 1 /*"
    assert span["data"] == {"db.query": "q", "body": FILTERED}


def test_breadcrumbs_may_be_a_plain_list():
    event = scrub_event({"breadcrumbs": [{"message": "token=abc"}]})

    assert event["breadcrumbs"] == [{"message": f"token={FILTERED}"}]


def test_an_event_with_nothing_to_clean_is_returned_as_it_is():
    assert scrub_event({}) == {}
    odd = {
        "request": {"headers": ["not", "a", "mapping"], "url": None},
        "logentry": {"params": "x"},
        "exception": {"values": None},
        "breadcrumbs": None,
    }
    assert scrub_event(odd) == odd


def test_a_user_agent_that_is_not_text_becomes_other():
    event = scrub_event({"request": {"headers": {"User-Agent": 5}}})

    assert event["request"]["headers"] == {"User-Agent": "other"}


@pytest.mark.parametrize("path", ["/scripture", "/scripture/quran/2/255", "/scripture/hadith/9"])
def test_an_event_on_a_scripture_route_loses_all_its_free_text(path):
    event = scrub_event(
        {
            "message": BASMALA,
            "request": {"url": f"https://api.tabsira.me{path}?q=x"},
            "logentry": {"message": "m", "formatted": BASMALA, "params": [BASMALA]},
            "exception": {
                "values": [{"type": "ValueError", "value": BASMALA}, {"type": "KeyError"}, "x"]
            },
            "extra": {"verse": BASMALA},
            "breadcrumbs": {"values": [{"message": BASMALA, "data": {"a": 1}}, "x"]},
            "spans": [{"description": "SELECT text FROM verses", "data": {"a": 1}}, "x"],
        }
    )

    assert event["message"] == SCRIPTURE_FILTERED
    assert event["logentry"] == {"message": SCRIPTURE_FILTERED, "formatted": SCRIPTURE_FILTERED}
    values = event["exception"]["values"]
    assert values[0] == {"type": "ValueError", "value": SCRIPTURE_FILTERED}
    assert values[1] == {"type": "KeyError"}
    assert "extra" not in event
    assert event["breadcrumbs"]["values"][0] == {"message": SCRIPTURE_FILTERED}
    assert event["spans"][0] == {"description": SCRIPTURE_FILTERED}
    # The route stays: it is what finds the bug.
    assert event["request"]["url"] == f"https://api.tabsira.me{path}"


def test_a_scripture_event_without_free_text_fields_is_still_handled():
    event = scrub_event({"request": {"url": "https://api.tabsira.me/scripture/x"}, "extra": {}})

    assert event == {"request": {"url": "https://api.tabsira.me/scripture/x"}}
    partial = scrub_event(
        {
            "request": {"url": "https://api.tabsira.me/scripture/x"},
            "logentry": {"message": BASMALA},
            "breadcrumbs": [{"data": {"a": BASMALA}}],
        }
    )
    assert partial["logentry"] == {"message": SCRIPTURE_FILTERED}
    assert partial["breadcrumbs"] == [{}]


@pytest.mark.parametrize(
    "event",
    [
        {"request": {"url": "https://api.tabsira.me/scripture-notes"}, "message": "m"},
        {"request": {"url": "https://api.tabsira.me/health"}, "message": "m"},
        {"request": {"url": 5}, "message": "m"},
        {"request": "no", "message": "m"},
        {"message": "m"},
    ],
)
def test_only_the_scripture_routes_are_blanked(event):
    assert scrub_event(event)["message"] == "m"


def test_a_transaction_is_named_after_its_verb_and_route():
    named = error_tracking.before_send(
        {"transaction": "/scripture/quran/{surah}", "request": {"method": "GET"}}
    )
    assert named["transaction"] == "GET /scripture/quran/{surah}"
    again = error_tracking.before_send({"transaction": "GET /health", "request": {"method": "GET"}})
    assert again["transaction"] == "GET /health"
    for event in (
        {"transaction": "/x", "request": {}},
        {"transaction": "/x"},
        {"transaction": 5, "request": {"method": "GET"}},
    ):
        assert error_tracking.before_send(event)["transaction"] == event["transaction"]


# ─── Naming ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("described", "version"),
    [
        ("v1.0.0-0-gabc1234", "1.0.0"),
        ("v1.0.0-32-gdbbab302", "1.0.0+32.gdbbab302"),
        ("2.1.0-3-g0123abc", "2.1.0+3.g0123abc"),
        ("02095ca5e7d1c3b9aa", "02095ca5e7d1"),
    ],
)
def test_git_describe_becomes_a_version_that_sorts_after_its_tag(described, version):
    assert error_tracking._describe_to_semver(described) == version


class FakeRun:
    def __init__(self, returncode: int = 0, stdout: str = "", error: Exception | None = None):
        self.returncode, self.stdout, self.error = returncode, stdout, error

    def __call__(self, *_args: Any, **_kwargs: Any) -> FakeRun:
        if self.error is not None:
            raise self.error
        return self


def test_git_is_asked_for_the_revision_and_may_have_nothing_to_say(monkeypatch):
    monkeypatch.setattr(subprocess, "run", FakeRun(stdout="v1.2.3-0-gabcdef0\n"))
    assert error_tracking._git_describe() == "v1.2.3-0-gabcdef0"
    monkeypatch.setattr(subprocess, "run", FakeRun(stdout="  \n"))
    assert error_tracking._git_describe() is None
    monkeypatch.setattr(subprocess, "run", FakeRun(returncode=128))
    assert error_tracking._git_describe() is None
    monkeypatch.setattr(subprocess, "run", FakeRun(error=FileNotFoundError("no git")))
    assert error_tracking._git_describe() is None
    monkeypatch.setattr(subprocess, "run", FakeRun(error=subprocess.TimeoutExpired("git", 5)))
    assert error_tracking._git_describe() is None


def test_the_release_names_the_service_and_the_version(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(error_tracking, "_git_describe", lambda: "v1.0.0-4-gabc1234")
    assert error_tracking.release_name("tabsira-api", settings, "0.1.0") == (
        "tabsira-api@1.0.0+4.gabc1234"
    )
    # No git history to read: the package version.
    monkeypatch.setattr(error_tracking, "_git_describe", lambda: None)
    assert error_tracking.release_name("tabsira-web", settings, "0.1.0") == "tabsira-web@0.1.0"
    # The setting wins over both, for a copy deployed without its .git.
    pinned = make_settings(glitchtip_release="2026.10.4")
    assert error_tracking.release_name("tabsira-api", pinned, "0.1.0") == "tabsira-api@2026.10.4"
    long = make_settings(glitchtip_release="v" * 100)
    assert len(error_tracking.release_name("s" * 150, long, "0.1.0")) == 200


# ─── Options and lifecycle ───────────────────────────────────────────


def test_the_options_send_no_personal_data_and_cut_the_trace_headers(make_settings):
    settings = make_settings(glitchtip_dsn=DSN, environment="test")

    options = error_tracking.build_options(settings, "0.1.0")

    assert options["dsn"] == DSN
    assert options["environment"] == "test"
    assert options["release"].startswith("tabsira-api@")
    assert options["send_default_pii"] is False
    assert options["max_request_body_size"] == "never"
    assert options["include_local_variables"] is False
    assert options["trace_propagation_targets"] == []
    assert options["auto_enabling_integrations"] is False
    assert options["before_send"] is error_tracking.before_send
    assert options["before_send_transaction"] is error_tracking.before_send
    assert options["transport"] is error_tracking.ShortTimeoutTransport
    assert error_tracking.ShortTimeoutTransport.TIMEOUT == 2
    # Errors only until a rate is set.
    assert "traces_sampler" not in options


def test_a_trace_rate_is_fixed_whatever_the_caller_asks(make_settings):
    options = error_tracking.build_options(
        make_settings(glitchtip_dsn=DSN, glitchtip_traces_sample_rate=0.25), "0.1.0"
    )

    assert options["traces_sampler"]({"parent_sampled": True}) == 0.25
    assert options["traces_sampler"]({"parent_sampled": False}) == 0.25


def test_without_a_dsn_the_sdk_is_never_started(make_settings, monkeypatch, caplog):
    def refuse(**_options: Any) -> None:
        raise AssertionError("the SDK was started without a DSN")

    monkeypatch.setattr(sentry_sdk, "init", refuse)
    monkeypatch.setattr(error_tracking, "_initialised", False)

    with caplog.at_level(logging.INFO, logger="tabsira.error_tracking"):
        started = error_tracking.init_error_tracking(make_settings(), "0.1.0")

    assert started is False
    assert "Error tracking is off" in caplog.text
    # Nothing to tag, flush or report either.
    error_tracking.tag_request("abc12345")
    error_tracking.shutdown_error_tracking()
    assert WebReporter(make_settings(), "0.1.0").enabled is False


def test_the_sdk_is_started_once_with_the_built_options(make_settings, monkeypatch):
    calls: list[dict[str, Any]] = []
    tags: list[tuple[str, str]] = []
    flushes: list[float] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **options: calls.append(options))
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda key, value: tags.append((key, value)))

    def fake_flush(timeout: float) -> None:
        flushes.append(timeout)

    monkeypatch.setattr(sentry_sdk, "flush", fake_flush)
    monkeypatch.setattr(error_tracking, "_initialised", False)
    settings = make_settings(glitchtip_dsn=DSN)

    assert error_tracking.init_error_tracking(settings, "0.1.0") is True
    assert error_tracking.init_error_tracking(settings, "0.1.0") is True
    error_tracking.tag_request("req-12345678")
    error_tracking.shutdown_error_tracking()

    assert len(calls) == 1
    assert calls[0]["dsn"] == DSN
    assert tags == [("area", "api"), ("request_id", "req-12345678")]
    assert flushes == [2]


def test_a_failing_sdk_leaves_the_service_running_without_reporting(
    make_settings, monkeypatch, caplog
):
    def explode(**_options: Any) -> None:
        raise RuntimeError("bad transport")

    monkeypatch.setattr(sentry_sdk, "init", explode)
    monkeypatch.setattr(error_tracking, "_initialised", False)

    with caplog.at_level(logging.WARNING, logger="tabsira.error_tracking"):
        started = error_tracking.init_error_tracking(make_settings(glitchtip_dsn=DSN), "0.1.0")

    assert started is False
    assert error_tracking._initialised is False
    assert "continuing without it" in caplog.text


async def test_a_server_error_reaches_glitchtip_cleaned(make_settings, recorder):
    settings = make_settings(glitchtip_dsn=DSN, glitchtip_release="9.9.9")
    app = create_app(settings)

    @app.get("/boom/{who}")
    async def boom(who: str) -> None:
        message = f"failed for token=abc123 and {BASMALA} {who}"
        raise RuntimeError(message)

    async with client_for(app) as http:
        response = await http.get(
            "/boom/42?email=a@b.c",
            headers={
                "Authorization": "Bearer xyz",
                "Cookie": "__Secure-tabsira_session=aaa",
                "User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit Chrome/120 Safari/537",
                "X-Forwarded-For": "1.2.3.4",
            },
        )
    sentry_sdk.flush()

    assert response.status_code == 500
    # One report, though both the handler's log record and the server raise it.
    assert len(recorder.events) == 1
    event = recorder.events[0]
    assert event["release"] == "tabsira-api@9.9.9"
    assert event["environment"] == "test"
    assert event["transaction"] == "GET /boom/{who}"
    assert event["tags"]["area"] == "api"
    assert event["tags"]["request_id"] == response.headers["x-request-id"]
    assert event["exception"]["values"][0]["value"] == (
        f"failed for token={FILTERED} and {ARABIC_FILTERED} 42"
    )
    assert event["request"]["url"] == "http://test/boom/42"
    assert event["request"]["headers"] == {
        "host": "test",
        "accept": "*/*",
        "user-agent": "chrome",
    }
    assert "user" not in event
    # The frames carry this test's own source lines, which hold the literals.
    frames = event["exception"]["values"][0].pop("stacktrace")["frames"]
    serialised = str(event)
    for secret in ("abc123", "xyz", "__Secure-tabsira_session", "1.2.3.4", "a@b.c", "بسم"):
        assert secret not in serialised
    # The code that failed is reported, not the values it was holding.
    assert all("vars" not in frame for frame in frames)


# ─── Browser reports ─────────────────────────────────────────────────


def test_a_v8_and_a_gecko_stack_become_frames_oldest_call_first():
    stack = "\n".join(
        [
            "TypeError: x is undefined",
            "    at render (https://tabsira.me/_next/static/app.js:10:20)",
            "    at https://tabsira.me/_next/static/app.js:30:40",
            "    at async Object.run (https://tabsira.me/_next/static/b.js:1:2)",
            "mount@https://tabsira.me/_next/static/c.js:5:6",
            "@https://tabsira.me/_next/static/d.js:7:8",
            "not a frame",
        ]
    )

    frames = error_tracking.parse_stack(stack)

    assert [(f["function"], f["lineno"], f["colno"]) for f in frames] == [
        ("<anonymous>", 7, 8),
        ("mount", 5, 6),
        ("async Object.run", 1, 2),
        ("<anonymous>", 30, 40),
        ("render", 10, 20),
    ]
    assert frames[-1]["filename"] == "https://tabsira.me/_next/static/app.js"
    assert all(frame["in_app"] for frame in frames)
    assert error_tracking.parse_stack("") == []


def a_report(**values: Any) -> ClientReport:
    return ClientReport(**{"message": "Boom", **values})


def test_an_error_report_becomes_an_event_with_its_frames():
    item = a_report(
        name="TypeError",
        stack="    at f (https://tabsira.me/a.js:1:2)",
        url="https://tabsira.me/insights/1?x=1",
        handled=False,
        level="fatal",
        context={"route": "/insights"},
        breadcrumbs=[ClientBreadcrumb(message="clicked", category="ui", timestamp=1.5)],
        release="v1.0.0-29-gabc1234",
    )

    event = error_tracking.web_event(item, request_id="req-1", user_agent="Firefox/130.0")

    assert event["platform"] == "javascript"
    assert event["level"] == "fatal"
    assert event["tags"] == {"area": "web", "browser": "firefox", "request_id": "req-1"}
    assert event["request"] == {"url": "https://tabsira.me/insights/1?x=1"}
    assert event["extra"] == {"context": {"route": "/insights"}}
    assert event["breadcrumbs"]["values"] == [
        {
            "type": "default",
            "category": "ui",
            "level": "info",
            "message": "clicked",
            "timestamp": 1.5,
        }
    ]
    exception = event["exception"]["values"][0]
    assert exception["type"] == "TypeError"
    assert exception["mechanism"] == {"type": "generic", "handled": False}
    assert exception["stacktrace"]["frames"][0]["lineno"] == 1
    assert event["release"] == "tabsira-web@1.0.0+29.gabc1234"


def test_a_stack_that_cannot_be_parsed_is_kept_as_text():
    event = error_tracking.web_event(a_report(stack="garbage"), request_id=None, user_agent=None)

    assert event["extra"] == {"stack": "garbage"}
    assert event["exception"]["values"][0]["type"] == "Error"
    assert "stacktrace" not in event["exception"]["values"][0]
    assert event["tags"] == {"area": "web", "browser": "other"}
    assert "request" not in event
    assert "release" not in event


def test_a_log_report_is_a_message_with_nothing_else():
    event = error_tracking.web_event(
        a_report(kind="log", level="warning", message="slow"), request_id=None, user_agent=None
    )

    assert event["message"] == "slow"
    assert "exception" not in event
    assert "extra" not in event
    assert "breadcrumbs" not in event


@pytest.fixture
def web_settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(glitchtip_web_dsn=WEB_DSN, glitchtip_release="1.0.0")


def test_the_web_reporter_sends_cleaned_events_from_its_own_scope(web_settings, recorder):
    reporter = WebReporter(web_settings, "0.1.0")
    items = [
        a_report(
            message=f"token=abc {BASMALA}",
            url="https://tabsira.me/scripture/quran/1?q=x",
            context={"gender": "man", "route": "/a?b=c"},
        ),
        a_report(kind="log", message="plain"),
    ]

    sent = reporter.report(items, request_id="req-9", user_agent="Mozilla Safari/605.1")
    reporter.flush()

    assert reporter.enabled
    assert sent == 2
    first, second = recorder.events
    assert first["exception"]["values"][0]["value"] == SCRIPTURE_FILTERED
    assert first["request"]["url"] == "https://tabsira.me/scripture/quran/1"
    assert first["release"] == "tabsira-web@1.0.0"
    assert first["tags"]["browser"] == "safari"
    assert second["message"] == "plain"
    assert "user" not in first
    # The first event is from a scripture page, so the context went too.
    assert "extra" not in first


def test_web_reports_are_cleaned_like_any_other_event(web_settings, recorder):
    reporter = WebReporter(web_settings, "0.1.0")

    reporter.report(
        [a_report(message=f"token=abc {BASMALA}", context={"gender": "man", "route": "/a?b=c"})],
        request_id=None,
        user_agent=None,
    )

    event = recorder.events[0]
    assert event["exception"]["values"][0]["value"] == f"token={FILTERED} {ARABIC_FILTERED}"
    assert event["extra"]["context"] == {"gender": FILTERED, "route": "/a"}


def test_the_web_client_is_built_once_and_reused(web_settings, recorder):
    reporter = WebReporter(web_settings, "0.1.0")

    assert reporter.report([a_report()], request_id=None, user_agent=None) == 1
    first = reporter._client
    assert reporter.report([a_report()], request_id=None, user_agent=None) == 1

    assert reporter._client is first
    assert len(recorder.events) == 2


def test_the_web_project_falls_back_to_the_api_project(make_settings, recorder):
    reporter = WebReporter(make_settings(glitchtip_dsn=DSN), "0.1.0")

    assert reporter.enabled
    assert reporter.report([a_report()], request_id=None, user_agent=None) == 1
    assert len(recorder.events) == 1


def test_without_a_dsn_a_report_is_dropped_and_no_client_is_built(make_settings, monkeypatch):
    def refuse(**_options: Any) -> None:
        raise AssertionError("a client was built without a DSN")

    monkeypatch.setattr(sentry_sdk, "Client", refuse)
    reporter = WebReporter(make_settings(), "0.1.0")

    assert reporter.enabled is False
    assert reporter.report([a_report()], request_id=None, user_agent=None) == 0
    reporter.flush()


def test_a_client_that_cannot_start_is_tried_once_and_reports_are_dropped(
    web_settings, monkeypatch, caplog
):
    attempts: list[int] = []

    def explode(**_options: Any) -> None:
        attempts.append(1)
        raise RuntimeError("bad option")

    monkeypatch.setattr(sentry_sdk, "Client", explode)
    reporter = WebReporter(web_settings, "0.1.0")

    with caplog.at_level(logging.WARNING, logger="tabsira.error_tracking"):
        assert reporter.report([a_report()], request_id=None, user_agent=None) == 0
        assert reporter.report([a_report()], request_id=None, user_agent=None) == 0

    assert attempts == [1]
    assert "browser reports are dropped" in caplog.text


def test_an_event_the_scrubber_drops_is_not_counted_as_sent(web_settings, recorder, monkeypatch):
    monkeypatch.setattr(error_tracking, "before_send", lambda _event, _hint=None: None)
    reporter = WebReporter(web_settings, "0.1.0")

    assert reporter.report([a_report()], request_id=None, user_agent=None) == 0
    assert recorder.events == []


def test_the_exception_type_the_breadcrumb_category_and_the_frames_are_scrubbed():
    event = {
        "exception": {
            "values": [
                {
                    "type": f"Error{BASMALA}",
                    "value": "x",
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "https://u:p@tabsira.me/a.js?token=abc&mail=a@b.co",
                                "function": f"handle{BASMALA}",
                            }
                        ]
                    },
                }
            ]
        },
        "breadcrumbs": {"values": [{"category": f"ui.{BASMALA}", "message": "m"}]},
    }

    error_tracking.scrub_event(event)

    value = event["exception"]["values"][0]
    assert value["type"] == f"Error{ARABIC_FILTERED}"
    frame = value["stacktrace"]["frames"][0]
    assert frame["filename"] == "https://tabsira.me/a.js"
    assert frame["function"] == f"handle{ARABIC_FILTERED}"
    assert event["breadcrumbs"]["values"][0]["category"] == f"ui.{ARABIC_FILTERED}"


def test_a_frame_without_text_fields_and_a_value_without_a_stack_are_left_alone():
    event = {"exception": {"values": [{"type": "E", "stacktrace": {"frames": [{"lineno": 1}, 7]}}]}}

    error_tracking.scrub_event(event)

    assert event["exception"]["values"][0]["stacktrace"]["frames"] == [{"lineno": 1}, 7]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("sent to ghazi@example.com now", "sent to [Email] now"),
        ("from 203.0.113.5 port", "from [Address] port"),
        ("from 2001:db8::1 port", "from [Address] port"),
        ("from 2001:0db8:0000:0000:0000:0000:0000:0001.", "from [Address]."),
        ("at 36.806389, 10.181667 here", "at [Coordinates] here"),
        ("at -33.8688;151.2093", "at [Coordinates]"),
        ("DETAIL:  Key (email)=(a@b.co) already exists.", "DETAIL: [Filtered]"),
        ("first\nDETAIL: Key (x)=(1)\nlast", "first\nDETAIL: [Filtered]\nlast"),
        ("app.js:10:20 and v1.2.3 and 12:30", "app.js:10:20 and v1.2.3 and 12:30"),
        ("Foo::bar and std::", "Foo::bar and std::"),
    ],
)
def test_personal_data_written_in_plain_text_is_masked(text, expected):
    assert error_tracking.scrub_text(text) == expected
