"""
Error reporting to GlitchTip, through the official Sentry SDK.

GlitchTip speaks the Sentry protocol, so the SDK does the sending. This module
owns what is collected, when, and how it is cleaned before it leaves the process
(decision 24). The rules:

1. Nothing is sent without a DSN. An empty `GLITCHTIP_DSN` starts no SDK and
   builds no client: there is no code path that could send anything.
2. No personal data. `send_default_pii` is off, no user is attached, the browser
   is reduced to its family, local variables are not captured and no request
   body, cookie, query string or `Authorization` header is ever sent.
3. Whatever a name says is private is masked: tokens and secrets, and the fields
   of a profile, a photo or a location (`is_private_name`). The masked value is
   the literal `[Filtered]`.
4. Arabic text is replaced wherever it appears. The product's own diagnostics are
   English, so Arabic in an error is a person's words or scripture, and neither
   may leave the server. Everything free-form of an event raised under
   `/scripture` is blanked as well.
5. Reporting never slows or breaks the product: the transport has a 2 s budget
   on the SDK's worker thread, and `init_error_tracking` catches everything.
6. A fixed trace sample rate (0 by default): a caller cannot force its request
   to be timed with a `sentry-trace` header, and outgoing requests carry no
   trace header to any other service.

Browsers have no DSN. They post their errors to `POST /client-errors`, which
validates, rate-limits and forwards them through `WebReporter` with the same
scrubbing.
"""

from __future__ import annotations

import logging
import re
import socket
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import sentry_sdk
from sentry_sdk.integrations.argv import ArgvIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.modules import ModulesIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.transport import HttpTransport

from src.config import Settings
from src.user_agent import user_agent_family

if TYPE_CHECKING:
    from sentry_sdk._types import Event

    from src.schemas.client_errors import ClientReport

log = logging.getLogger("tabsira.error_tracking")

API_SERVICE = "tabsira-api"
WEB_SERVICE = "tabsira-web"
FILTERED = "[Filtered]"
ARABIC_FILTERED = "[Arabic text]"
SCRIPTURE_FILTERED = "[Scripture route: text filtered]"
# Events raised under this path belong to the scripture routes, whose answers are
# Quran and hadith text.
SCRIPTURE_PATH = "/scripture"

# The name of a field, header, query parameter or `name=value` pair says it is a
# secret when it holds one of these words anywhere, or ends in "pw".
SECRET_NAME = re.compile(
    r"pass|secret|token|checksum|api[_-]?key|authori[sz]ation|cookie|session|csrf|credential",
    re.IGNORECASE,
)
# What a name says about whose it is: the profile, a photo, a place, a typed text.
# A word counts when nothing alphanumeric touches it, so `context` is not `text`.
PRIVATE_NAME = re.compile(
    r"(?<![a-z0-9])(?:e-?mail|display[_-]?name|age[_-]?range|religio\w*|gender|goals?"
    r"|knowledge[_-]?level|profile|photos?|images?|pictures?|avatar|exif|gps|latitude"
    r"|longitude|lat|lng|lon|location|coordinates?|address|phone|verses?|hadiths?"
    r"|scripture|quran|text|body|caption|prompt|search|notes?)(?![a-z0-9])",
    re.IGNORECASE,
)
# The Arabic script, with the marks that follow a letter. A run goes from its
# first to its last letter and keeps the spaces and Arabic punctuation between.
_ARABIC_LETTERS = r"\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff"
# Zero-width joiners sit inside Arabic words and between them.
_JOINERS = r"\u200c\u200d"
ARABIC_RUN = re.compile(
    f"[{_ARABIC_LETTERS}](?:[{_ARABIC_LETTERS}\\s{_JOINERS}]*[{_ARABIC_LETTERS}])?"
)
# `?name=value&...` up to the next space or quote: a query string, wherever it is
# written (a URL, a path, a log line). Its names are not looked at; all of it goes.
_QUERY_STRING = re.compile(r"\?[\w%.\-\[\]]+=[^\s\"'<>]*")
# The `scheme://user:password@host:port` front of an address, and the part of it
# that is only credentials.
_ORIGIN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/]*")
_USERINFO = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*://)[^/]*@")
# What ends a pair's value, besides whitespace.
_VALUE_STOPS = frozenset("&\"'<>")

# The only request headers that are sent: what is needed to understand a failure
# and nothing that identifies a visitor. The user agent is reduced to its family.
_KEPT_HEADERS = frozenset({"content-type", "content-length", "accept", "host", "origin"})

# git describe --long: <tag>-<commits since>-g<sha>
_DESCRIBE = re.compile(r"^(?P<tag>.+?)-(?P<count>\d+)-g(?P<sha>[0-9a-f]+)$")
_MAX_RELEASE_LENGTH = 200

# Browser stack traces. V8 (Chrome, Edge, Node): "    at fn (url:line:col)" or
# "    at url:line:col". Gecko and JavaScriptCore: "fn@url:line:col".
_V8_FRAME = re.compile(
    r"^\s*at (?:(?P<fn>.+?) \()?(?P<url>[^()]+?):(?P<line>\d+):(?P<col>\d+)\)?\s*$"
)
_GECKO_FRAME = re.compile(r"^(?P<fn>[^@]*)@(?P<url>.+?):(?P<line>\d+):(?P<col>\d+)\s*$")

_initialised = False


class ShortTimeoutTransport(HttpTransport):
    """
    The SDK's transport with a 2 s budget instead of 30 s.

    Sending happens on the SDK's worker thread, so a slow GlitchTip never holds a
    request; the budget only bounds how long that thread, and the flush at
    shutdown, can wait on it.
    """

    TIMEOUT = 2


# ─── Scrubbing ───────────────────────────────────────────────────────


def is_secret_name(name: str) -> bool:
    """Whether a field, header or parameter name denotes a secret."""
    return SECRET_NAME.search(name) is not None or name.lower().endswith("pw")


def is_private_name(name: str) -> bool:
    """Whether a name denotes a secret, or something that belongs to a person."""
    return is_secret_name(name) or PRIVATE_NAME.search(name) is not None


def _is_name_char(char: str) -> bool:
    return char.isalnum() or char in "_.-[]"


def _scrub_pairs(text: str) -> str:
    """
    Mask the value of every `name=value` pair whose name is private.

    One pass, left to right, never re-reading a character: a regex version
    retried names at every position of a long run with no "=" and took 20
    seconds on a 20,000-character report.
    """
    out: list[str] = []
    i, end = 0, len(text)
    while i < end:
        if not _is_name_char(text[i]):
            out.append(text[i])
            i += 1
            continue
        name_end = i
        while name_end < end and _is_name_char(text[name_end]):
            name_end += 1
        if name_end == end or text[name_end] != "=":
            out.append(text[i:name_end])
            i = name_end
            continue
        value_end = name_end + 1
        while (
            value_end < end
            and text[value_end] not in _VALUE_STOPS
            and not text[value_end].isspace()
        ):
            value_end += 1
        name = text[i:name_end]
        out.append(f"{name}={FILTERED}" if is_private_name(name) else text[i:value_end])
        i = value_end
    return "".join(out)


def scrub_text(text: str) -> str:
    """
    Clean a string: no Arabic, no query string, no private `name=value`.

    The query string goes whole, whatever its names: a page address, a place
    search or a verse reference in it says what a person did.
    """
    without_arabic = ARABIC_RUN.sub(ARABIC_FILTERED, text)
    return _scrub_pairs(_QUERY_STRING.sub("", without_arabic))


def scrub_url(url: str) -> str:
    """
    Return `url` without credentials, query string and fragment, then scrubbed as text.

    Written with plain splits, not a URL parser: the address comes from a browser
    and a parser raises on a malformed one.
    """
    bare = url.split("#", 1)[0].split("?", 1)[0]
    return scrub_text(_USERINFO.sub(r"\1", bare))


def _path_of(url: str) -> str:
    """Return the path of an address, whatever else is wrong with it."""
    return _ORIGIN.sub("", url.split("#", 1)[0].split("?", 1)[0])


def scrub_value(value: Any) -> Any:
    """Scrub a value of any shape: strings as text, bytes dropped, containers recursively."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, bytes | bytearray):
        return FILTERED
    if isinstance(value, Mapping):
        return scrub_mapping(value)
    if isinstance(value, list | tuple | set | frozenset):
        return [scrub_value(item) for item in value]
    return value


def scrub_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """Walk a mapping: a private key has its value replaced, other values are scrubbed."""
    return {
        key: FILTERED if is_private_name(str(key)) else scrub_value(value)
        for key, value in data.items()
    }


def _scrub_str_keys(container: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if isinstance(container.get(key), str):
            container[key] = scrub_text(container[key])


def _scrub_mapping_keys(container: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if isinstance(container.get(key), Mapping):
            container[key] = scrub_mapping(container[key])


def _scrub_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    kept: dict[str, Any] = {}
    for name, value in headers.items():
        lowered = str(name).lower()
        if lowered == "user-agent":
            kept[name] = user_agent_family(value if isinstance(value, str) else None)
        elif lowered in _KEPT_HEADERS:
            kept[name] = scrub_value(value)
    return kept


def _scrub_request(event: Any) -> None:
    request = event.get("request")
    if not isinstance(request, dict):
        return
    # Never sent, whatever they hold: the body, the cookies, the query string and
    # the WSGI/ASGI environment (which carries the client address).
    for key in ("data", "cookies", "query_string", "env"):
        request.pop(key, None)
    if isinstance(request.get("url"), str):
        request["url"] = scrub_url(request["url"])
    if isinstance(request.get("headers"), Mapping):
        request["headers"] = _scrub_headers(request["headers"])


def _scrub_logentry(event: Any) -> None:
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        _scrub_str_keys(logentry, ("message", "formatted"))
        if isinstance(logentry.get("params"), list | tuple):
            logentry["params"] = scrub_value(logentry["params"])


def _scrub_exception_values(event: Any) -> None:
    exception = event.get("exception")
    if isinstance(exception, dict):
        for value in exception.get("values") or []:
            if isinstance(value, dict):
                _scrub_str_keys(value, ("value",))


def _scrub_each(items: Any, str_key: str) -> None:
    """Scrub `str_key` and `data` of every dict in a breadcrumb or span list."""
    for item in items or []:
        if isinstance(item, dict):
            _scrub_str_keys(item, (str_key,))
            _scrub_mapping_keys(item, ("data",))


def _breadcrumb_list(event: Any) -> Any:
    breadcrumbs = event.get("breadcrumbs")
    return breadcrumbs.get("values") if isinstance(breadcrumbs, dict) else breadcrumbs


def _is_scripture_event(event: Any) -> bool:
    request = event.get("request")
    url = request.get("url") if isinstance(request, dict) else None
    if not isinstance(url, str):
        return False
    path = _path_of(url)
    return path == SCRIPTURE_PATH or path.startswith(f"{SCRIPTURE_PATH}/")


def _blank_each(items: Any, str_key: str) -> None:
    for item in items or []:
        if isinstance(item, dict):
            if isinstance(item.get(str_key), str):
                item[str_key] = SCRIPTURE_FILTERED
            item.pop("data", None)


def _blank_free_text(event: Any) -> None:
    """
    Replace everything free-form in an event raised on a scripture route.

    What these routes answer is Quran and hadith text, which the error tracker
    must never hold. The type of the exception, its frames and the route stay,
    which is all that is needed to find the bug.
    """
    if isinstance(event.get("message"), str):
        event["message"] = SCRIPTURE_FILTERED
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = SCRIPTURE_FILTERED
        logentry.pop("params", None)
    exception = event.get("exception")
    if isinstance(exception, dict):
        for value in exception.get("values") or []:
            if isinstance(value, dict) and isinstance(value.get("value"), str):
                value["value"] = SCRIPTURE_FILTERED
    event.pop("extra", None)
    _blank_each(_breadcrumb_list(event), "message")
    _blank_each(event.get("spans"), "description")


def scrub_event(event: Any, _hint: Any = None) -> Any:
    """
    Clean an error or transaction event in place and return it.

    Covers the request (URL, headers; no body, cookies or query string), the
    message, each exception value, `extra`, `tags`, `contexts`, every breadcrumb
    and, for transactions, every span's description and data. The user, if the
    SDK attached one, is dropped.
    """
    scripture = _is_scripture_event(event)
    _scrub_request(event)
    event.pop("user", None)
    if scripture:
        _blank_free_text(event)
    _scrub_str_keys(event, ("message", "transaction"))
    _scrub_logentry(event)
    _scrub_exception_values(event)
    _scrub_mapping_keys(event, ("extra", "tags", "contexts"))
    _scrub_each(_breadcrumb_list(event), "message")
    _scrub_each(event.get("spans"), "description")
    return event


def _name_after_route(event: Any) -> None:
    """Prefix the route pattern with the HTTP verb: `GET /scripture/quran/{surah}`."""
    transaction = event.get("transaction")
    request = event.get("request")
    method = request.get("method") if isinstance(request, dict) else None
    if (
        isinstance(transaction, str)
        and isinstance(method, str)
        and not transaction.startswith(f"{method} ")
    ):
        event["transaction"] = f"{method} {transaction}"


def before_send(event: Any, hint: Any = None) -> Any:
    """Errors and transactions: name after the matched route so they group, then scrub."""
    _name_after_route(event)
    return scrub_event(event, hint)


# ─── Naming ──────────────────────────────────────────────────────────


def _describe_to_semver(described: str) -> str:
    """
    Turn `git describe --tags --long` output into a sortable version.

    `1.0.0-32-gdbbab302` would read as a pre-release of 1.0.0, older than 1.0.0.
    `1.0.0+32.gdbbab302` sorts after it, which is what it is.
    """
    match = _DESCRIBE.match(described)
    if match is None:
        # No tag anywhere in history: `--always` gives the bare commit.
        return described[:12]
    tag = match["tag"].removeprefix("v")
    if match["count"] == "0":
        return tag
    return f"{tag}+{match['count']}.g{match['sha']}"


def _git_describe() -> str | None:
    """Ask git for the current revision; None where there is no git or no checkout."""
    root = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "describe", "--tags", "--long", "--always"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def release_name(service: str, settings: Settings, version: str) -> str:
    """
    `<service>@<version>` for this build, at most 200 characters.

    `GLITCHTIP_RELEASE` overrides the version when set, which is what a copy
    deployed without its `.git` should do. Otherwise git describes the checkout,
    and failing that `version`, the package version. The service name is part of
    it because GlitchTip shares releases across an organisation.
    """
    chosen = settings.glitchtip_release
    if not chosen:
        described = _git_describe()
        chosen = _describe_to_semver(described) if described else version
    return f"{service}@{chosen}"[:_MAX_RELEASE_LENGTH]


# ─── Lifecycle ───────────────────────────────────────────────────────


def _integrations() -> list[Any]:
    return [
        StarletteIntegration(transaction_style="url"),
        FastApiIntegration(transaction_style="url"),
        SqlalchemyIntegration(),
        # Records from INFO travel with the next issue as breadcrumbs; from ERROR
        # they become an issue. Nothing is sent as a log entry of its own.
        LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
    ]


def _common_options(settings: Settings, service: str, version: str) -> dict[str, Any]:
    return {
        "environment": str(settings.environment),
        "release": release_name(service, settings, version),
        "server_name": socket.gethostname(),
        "sample_rate": 1.0,
        "send_default_pii": False,
        "max_request_body_size": "never",
        # Frames carry their code, never the values of their local variables.
        "include_local_variables": False,
        "shutdown_timeout": 2,
        "auto_session_tracking": False,
        "send_client_reports": False,
        "enable_metrics": False,
        "enable_logs": False,
        # No `sentry-trace` or `baggage` header ever leaves for another service.
        "trace_propagation_targets": [],
        "transport": ShortTimeoutTransport,
        "before_send": before_send,
        "before_send_transaction": before_send,
    }


def build_options(settings: Settings, version: str) -> dict[str, Any]:
    """Return the arguments of `sentry_sdk.init` for the API process."""
    options = _common_options(settings, API_SERVICE, version)
    rate = settings.glitchtip_traces_sample_rate
    if rate > 0:
        # Fixed, whatever the incoming `sentry-trace` header says.
        options["traces_sampler"] = lambda _context: rate
    return {
        "dsn": settings.glitchtip_dsn.get_secret_value(),
        "project_root": str(Path(__file__).resolve().parent.parent),
        "in_app_include": ["src"],
        "auto_enabling_integrations": False,
        # `sys.argv` can carry an address or a path; the package list says nothing we need.
        "disabled_integrations": [ArgvIntegration, ModulesIntegration],
        "integrations": _integrations(),
        **options,
    }


def init_error_tracking(settings: Settings, version: str) -> bool:
    """
    Start the SDK once, before the application is built. Never raises.

    The Starlette and FastAPI integrations hook the framework as the application
    is assembled, so a later start would report nothing. Returns whether
    reporting is on: false without a DSN, and false when the SDK refuses to start
    (the service then runs without it).
    """
    global _initialised  # noqa: PLW0603

    if not settings.glitchtip_configured:
        log.info("Error tracking is off: GLITCHTIP_DSN is empty.")
        return False
    if _initialised:
        return True
    try:
        sentry_sdk.init(**build_options(settings, version))
    except Exception:
        # Deliberately broad: whatever went wrong, the service still serves.
        log.warning("GlitchTip start failed; continuing without it.", exc_info=True)
        return False
    sentry_sdk.set_tag("area", "api")
    _initialised = True
    log.info("Error tracking started, release %s.", release_name(API_SERVICE, settings, version))
    return True


def shutdown_error_tracking() -> None:
    """Let the last buffered events out. Never raises."""
    if _initialised:
        sentry_sdk.flush(timeout=2)


def tag_request(request_id: str) -> None:
    """Tag the current request's events with the id the access log and the response carry."""
    if _initialised:
        sentry_sdk.set_tag("request_id", request_id)


# ─── Browser reports ─────────────────────────────────────────────────


def parse_stack(stack: str) -> list[dict[str, Any]]:
    """
    Turn a browser stack string into Sentry frames, oldest call first.

    Lines that match neither the V8 nor the Gecko shape are skipped; a stack with
    no parseable line yields no frames, and the caller keeps the raw text.
    """
    frames: list[dict[str, Any]] = []
    for raw in stack.splitlines():
        match = _V8_FRAME.match(raw) or _GECKO_FRAME.match(raw)
        if match is None:
            continue
        frames.append(
            {
                "filename": match["url"].strip(),
                "function": (match["fn"] or "").strip() or "<anonymous>",
                "lineno": int(match["line"]),
                "colno": int(match["col"]),
                "in_app": True,
            }
        )
    frames.reverse()
    return frames


def _web_breadcrumbs(item: ClientReport) -> dict[str, Any]:
    return {
        "values": [
            {
                "type": "default",
                "category": crumb.category,
                "level": crumb.level,
                "message": crumb.message,
                "timestamp": crumb.timestamp,
            }
            for crumb in item.breadcrumbs
        ]
    }


def _add_web_error(event: dict[str, Any], item: ClientReport) -> None:
    """Attach the exception, with its parsed frames or, failing that, the raw stack."""
    exception: dict[str, Any] = {
        "type": item.name or "Error",
        "value": item.message,
        "mechanism": {"type": "generic", "handled": item.handled},
    }
    frames = parse_stack(item.stack) if item.stack else []
    if frames:
        exception["stacktrace"] = {"frames": frames}
    elif item.stack:
        event["extra"]["stack"] = item.stack
    event["exception"] = {"values": [exception]}


def web_event(
    item: ClientReport, *, request_id: str | None, user_agent: str | None
) -> dict[str, Any]:
    """
    Build the Sentry event for one browser report.

    The page address is the only request detail kept, and the browser is a tag
    holding its family. Scrubbing happens in `before_send`.
    """
    tags: dict[str, str] = {"area": "web", "browser": user_agent_family(user_agent)}
    if request_id:
        tags["request_id"] = request_id
    event: dict[str, Any] = {
        "platform": "javascript",
        "level": item.level,
        "logger": "web",
        "tags": tags,
        "extra": {},
    }
    if item.url:
        event["request"] = {"url": item.url}
    if item.context:
        event["extra"]["context"] = dict(item.context)
    if item.breadcrumbs:
        event["breadcrumbs"] = _web_breadcrumbs(item)
    if item.kind == "error":
        _add_web_error(event, item)
    else:
        event["message"] = item.message
    if item.release:
        # The browser's own build, which can lag or lead the API's after a deploy.
        version = _describe_to_semver(item.release).removeprefix("v")
        event["release"] = f"{WEB_SERVICE}@{version}"[:_MAX_RELEASE_LENGTH]
    if not event["extra"]:
        del event["extra"]
    return event


class WebReporter:
    """
    Forwards the errors browsers post to the GlitchTip project of the web app.

    The client is built on first use, once. It has no integrations and events are
    captured with no scope, so nothing of the API request that carried the report (its
    breadcrumbs, its transaction) leaks into a browser event.
    """

    def __init__(self, settings: Settings, version: str) -> None:
        self._settings = settings
        self._version = version
        self._client: sentry_sdk.Client | None = None
        self._failed = False

    @property
    def enabled(self) -> bool:
        """Whether reports are forwarded: a DSN is set. Otherwise they are dropped."""
        return bool(self._settings.glitchtip_web_dsn_value)

    def _get_client(self) -> sentry_sdk.Client | None:
        if self._client is not None:
            return self._client
        if self._failed or not self.enabled:
            return None
        try:
            self._client = sentry_sdk.Client(
                dsn=self._settings.glitchtip_web_dsn_value,
                default_integrations=False,
                auto_enabling_integrations=False,
                **_common_options(self._settings, WEB_SERVICE, self._version),
            )
        except Exception:
            self._failed = True
            log.warning("GlitchTip web client could not start; browser reports are dropped.")
            return None
        return self._client

    def report(
        self, items: list[ClientReport], *, request_id: str | None, user_agent: str | None
    ) -> int:
        """Forward the reports. Returns how many were sent; 0 when off or unable."""
        client = self._get_client()
        if client is None:
            return 0
        sent = 0
        for item in items:
            event = web_event(item, request_id=request_id, user_agent=user_agent)
            # No scope at all: any scope the SDK merges in carries the API request's event
            # processors once the API SDK has started, and they would replace the report's
            # own page address with this endpoint's and add its headers.
            if client.capture_event(cast("Event", event)) is not None:
                sent += 1
        return sent

    def flush(self) -> None:
        """Let the last buffered events out. Never raises."""
        if self._client is not None:
            self._client.flush(timeout=2)
