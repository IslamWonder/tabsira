"""
The production checklist of `python -m src.cli.check_config`.

Loading the settings already refuses what is plainly unfit for production (a
development host, an empty key, a short secret). This goes further, the way an
operator reads a `.env` before a deploy: each setting is reported as `ok`,
`fix` (required, the deploy stops), `check` (recommended) or `off` (optional),
grouped by what it is for. Secrets are never printed, only whether they are set.

With `--live` each service is also tried for real: the database, Redis (and that
it keeps nothing on disk), the AI provider's key, the detector, the mail server
and the public names of the site. Nothing here sends a photo, a mail or a
message, and nothing reaches a service the application does not already call.
"""

from __future__ import annotations

import asyncio
import re
import smtplib
import socket
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import psycopg
import redis
from sqlalchemy.engine import make_url

from src.config import AiStage, RerankerKind, Settings, checkout_root
from src.features import FeatureFlag
from src.services import turnstile_service

REQUIRED, RECOMMENDED, OPTIONAL = "required", "recommended", "optional"
LIVE_TIMEOUT = 10.0
# Text that means "the owners have not filled this in yet" (deploy/env.production.example).
PLACEHOLDERS = ("CHANGE_ME", "DATA_HOST_VPN_IP", "APP_HOST_VPN_IP")
LOOPBACK = {"127.0.0.1", "::1"}
MIN_PASSWORD_LENGTH = 16
# PostgreSQL's default max_connections; the pools of every process must fit well under it.
CONNECTION_BUDGET = 100
GA_ID = re.compile(r"^G-[A-Z0-9]{6,}$")
# The production file mirrors this example key for key: a key the example has and
# the file lacks is one the owners never saw (AGENTS.md, «Add every new configuration key»).
EXAMPLE_FILE = checkout_root() / "deploy" / "env.production.example"
KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


@dataclass(frozen=True)
class Check:
    """One line of the report."""

    area: str
    name: str
    level: str
    ok: bool
    detail: str = ""


Add = Callable[..., None]


def _host(url: str) -> str:
    return urlsplit(url or "").hostname or ""


def _apex(url: str) -> str:
    """Return the registrable part of a site address: `https://tabsira.me` gives `tabsira.me`."""
    return _host(url).removeprefix("www.")


def _positive_int(raw: str | None, default: int) -> int | None:
    """Return the integer in `raw` (`default` when empty); None when it is not a positive integer."""
    text = (raw or "").strip()
    if not text:
        return default
    return int(text) if text.isdigit() and int(text) > 0 else None


def example_keys(path: Path | None = None) -> set[str] | None:
    """Return the keys of the production example, or None when the file is not beside the code."""
    path = EXAMPLE_FILE if path is None else path
    if not path.is_file():
        return None
    return set(KEY_LINE.findall(path.read_text(encoding="utf-8")))


def _file_checks(_settings: Settings, env: Mapping[str, str], add: Add) -> None:
    """Check the file against the example it was copied from: nothing new missing, nothing stale."""
    keys = example_keys()
    if keys is None:
        add(
            "File",
            "deploy/env.production.example is beside the code",
            RECOMMENDED,
            False,
            "the keys of the file cannot be compared with the example",
        )
        return
    missing = sorted(keys - env.keys())
    add(
        "File",
        "every key of deploy/env.production.example is in the file",
        REQUIRED,
        not missing,
        ", ".join(missing)
        or "a key added to the code is set here before it is deployed, empty when optional",
    )
    unknown = sorted(env.keys() - keys)
    add(
        "File",
        "no key the example does not know",
        RECOMMENDED,
        not unknown,
        ", ".join(unknown) or "a misspelt or removed key would be read by nothing",
    )


def _api_checks(settings: Settings, env: Mapping[str, str], add: Add) -> None:
    """Check the API itself: where it listens, its public names and who may call it."""
    placeholders = sorted(k for k, v in env.items() if any(p in v for p in PLACEHOLDERS))
    add(
        "API",
        "no placeholder left in the file",
        REQUIRED,
        not placeholders,
        ", ".join(placeholders) or "every CHANGE_ME and address placeholder is filled in",
    )
    add(
        "API",
        "API_HOST is loopback",
        REQUIRED,
        settings.api_host in LOOPBACK,
        "nginx is on this host and the only public face",
    )
    apex = _apex(settings.site_url)
    add(
        "API",
        "SITE_URL / API_URL / ADMIN_URL share one domain",
        REQUIRED,
        bool(apex)
        and _host(settings.api_url) == f"api.{apex}"
        and _host(settings.admin_url) == f"admin.{apex}",
        f"{apex or 'the site'}, api.{apex or '…'}, admin.{apex or '…'}",
    )
    add(
        "API",
        "CORS_ORIGINS holds the site and nothing else",
        REQUIRED,
        list(settings.cors_origins) == [settings.site_url.rstrip("/")],
        "credentialed requests: one origin, https",
    )
    domain = settings.session_cookie_domain.lstrip(".")
    add(
        "API",
        "SESSION_COOKIE_DOMAIN covers the site and the API",
        REQUIRED,
        bool(domain)
        and _host(settings.site_url).endswith(domain)
        and _host(settings.api_url).endswith(domain),
        f".{apex}: shared by the web and api subdomains",
    )
    add(
        "API",
        "ADMIN_REQUIRE_TWO_FACTOR=true",
        RECOMMENDED,
        settings.admin_require_two_factor,
        "once the first admin has enrolled",
    )
    add(
        "API",
        "camera_anchor is not in ENABLED_FEATURES",
        RECOMMENDED,
        not settings.is_enabled(FeatureFlag.CAMERA_ANCHOR),
        "camera level C is off until it is proven on devices",
    )
    add(
        "API",
        "GEO_APPROX_CELL_METERS is at least 1000",
        RECOMMENDED,
        settings.geo_approx_cell_meters >= 1000,
        "the public location is rounded to this grid",
    )


def _data_checks(settings: Settings, env: Mapping[str, str], add: Add) -> None:
    """Check the stores: PostgreSQL and Redis over the VPN, and how the workers share them."""
    primary = make_url(settings.database_url.get_secret_value())
    sync_raw = settings.sync_database_url
    sync = make_url(sync_raw.get_secret_value()) if sync_raw is not None else None
    add(
        "Data",
        "SYNC_DATABASE_URL names the same database",
        REQUIRED,
        sync is not None
        and (sync.host, sync.port, sync.database, sync.username)
        == (primary.host, primary.port, primary.database, primary.username),
        "migrations and tools use it; same host, name and user as DATABASE_URL",
    )
    add(
        "Data",
        "database password is long",
        RECOMMENDED,
        len(primary.password or "") >= MIN_PASSWORD_LENGTH,
        f"{MIN_PASSWORD_LENGTH}+ characters, generated by deploy/provision-postgres.sh",
    )
    add(
        "Data",
        "REDIS_PASSWORD is long",
        RECOMMENDED,
        len(settings.redis_password.get_secret_value()) >= MIN_PASSWORD_LENGTH,
        f"{MIN_PASSWORD_LENGTH}+ characters, generated by deploy/provision-redis.sh",
    )
    workers = _positive_int(env.get("API_WORKERS"), 2)
    pool = settings.db_pool_size + settings.db_max_overflow
    add(
        "Data",
        "API_WORKERS is a positive number",
        REQUIRED,
        workers is not None,
        "gunicorn workers; the deploy brings the live pool to it",
    )
    if workers is not None:
        add(
            "Data",
            "database connections fit under max_connections",
            RECOMMENDED,
            workers * pool + pool <= CONNECTION_BUDGET,
            f"{workers} workers and the scan worker x {pool} = up to {workers * pool + pool}"
            f" of {CONNECTION_BUDGET}",
        )


def _storage_checks(settings: Settings, _env: Mapping[str, str], add: Add) -> None:
    """Check that photos are kept in S3 and nowhere else."""
    add(
        "Storage",
        "STORAGE_BACKEND resolves to s3",
        REQUIRED,
        settings.resolved_storage_backend == "s3",
        "photos are kept in S3 and nowhere else",
    )


def _ai_checks(settings: Settings, _env: Mapping[str, str], add: Add) -> None:
    """Check the AI provider: every stage of the active one has a model."""
    provider = settings.ai
    needed = [
        stage
        for stage in AiStage
        if stage is not AiStage.GUARD
        and (stage is not AiStage.RERANK or settings.reranker is RerankerKind.LLM)
    ]
    missing = [stage.value for stage in needed if not provider.model_for(stage)]
    add(
        "AI",
        f"every stage has a model ({settings.ai_provider.value})",
        REQUIRED,
        not missing,
        # A blank AI_*__PLANNER_MODEL= line overrides the default with nothing.
        ("no model for: " + ", ".join(missing))
        if missing
        else "vision, planner, verify, compose, chat, embedding",
    )
    add(
        "AI",
        "the content guard has a model",
        RECOMMENDED,
        bool(provider.guard_model),
        "image moderation of a scan",
    )


def _mail_checks(settings: Settings, _env: Mapping[str, str], add: Add) -> None:
    """Account mail: verification and password reset."""
    add(
        "Mail",
        "SMTP_HOST is set",
        REQUIRED,
        settings.smtp_configured,
        "without it nobody can verify an address or reset a password",
    )
    apex = _apex(settings.site_url)
    sender = settings.mail_from.rstrip(">").rsplit("@", 1)[-1]
    add(
        "Mail",
        "MAIL_FROM is on the site's domain",
        RECOMMENDED,
        sender == apex,
        f"@{apex}: SPF, DKIM and DMARC are set up for it",
    )
    for key, address in (
        ("SUPPORT_EMAIL", settings.support_email),
        ("PRIVACY_EMAIL", settings.privacy_email),
    ):
        add(
            "Mail",
            f"{key} is on the site's domain",
            RECOMMENDED,
            address.rsplit("@", 1)[-1] == apex,
        )


def _signin_checks(settings: Settings, _env: Mapping[str, str], add: Add) -> None:
    """Google sign-in, when it is on."""
    if not settings.google_configured:
        add("Sign-in", "Google", OPTIONAL, False, "not configured")
        return
    expected = f"{settings.api_url.rstrip('/')}/auth/google/callback"
    add(
        "Sign-in",
        "GOOGLE_REDIRECT_URI",
        REQUIRED,
        settings.google_redirect_uri == expected,
        f"{expected}, also registered in the Google console",
    )


def _web_checks(settings: Settings, env: Mapping[str, str], add: Add) -> None:
    """Check the web build and server: baked addresses, ports, analytics."""
    for key, expected in (
        ("NEXT_PUBLIC_SITE_URL", settings.site_url),
        ("NEXT_PUBLIC_API_URL", settings.api_url),
    ):
        value = env.get(key, "").strip().rstrip("/")
        add(
            "Web",
            key,
            REQUIRED,
            value in {"", expected.rstrip("/")},
            f"{expected}: baked into the build, so a wrong one is wrong in every canonical and share tag",
        )
    add(
        "Web",
        "WEB_INSTANCES / WEB_PORT",
        REQUIRED,
        (
            env.get("WEB_INSTANCES", "").strip() in {"", "max"}
            or _positive_int(env.get("WEB_INSTANCES"), 2) is not None
        )
        and _positive_int(env.get("WEB_PORT"), 3000) is not None,
        "pm2 instances (a number or max) and the loopback port nginx proxies to",
    )
    ga = env.get("GA_MEASUREMENT_ID", "").strip()
    add(
        "Web",
        "GA_MEASUREMENT_ID",
        OPTIONAL if not ga else RECOMMENDED,
        bool(ga) and bool(GA_ID.match(ga)),
        "Google Analytics, only after consent" if not ga else "looks like G-XXXXXXXXXX",
    )
    add(
        "Web",
        "CLARITY_PROJECT_ID",
        OPTIONAL,
        bool(env.get("CLARITY_PROJECT_ID", "").strip()),
        "heatmaps, only after consent",
    )
    add(
        "Web",
        "GLITCHTIP_DSN",
        RECOMMENDED,
        settings.glitchtip_configured,
        "error reports from the API and the browser",
    )
    add(
        "Services",
        "TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY",
        RECOMMENDED,
        bool(settings.turnstile_site_key.strip()) and settings.turnstile_enabled,
        "bot check on sign-up, sign-in, the mail forms and support",
    )
    add(
        "Services",
        "DETECTOR_URL is loopback",
        RECOMMENDED,
        _host(settings.detector_url) in LOOPBACK,
        "the detector runs on this host and is never public",
    )


def run_checks(settings: Settings, env: Mapping[str, str]) -> list[Check]:
    """Every production check, against the loaded settings and the raw file."""
    out: list[Check] = []

    def add(area: str, name: str, level: str, ok: bool, detail: str = "") -> None:
        out.append(Check(area, name, level, ok, detail))

    for section in (
        _file_checks,
        _api_checks,
        _data_checks,
        _storage_checks,
        _ai_checks,
        _mail_checks,
        _signin_checks,
        _web_checks,
    ):
        section(settings, env, add)
    return out


# ─── Live probes ────────────────────────────────────────────────────


class ProbeError(RuntimeError):
    """A service answered, but not the way the setting needs."""


def _short(exc: BaseException) -> str:
    """One line of an error, never a traceback and never more than a sentence."""
    text = " ".join(str(exc).split()) or type(exc).__name__
    return text[:200]


def _database(settings: Settings, _env: Mapping[str, str]) -> str:
    source = settings.sync_database_url or settings.database_url
    url = make_url(source.get_secret_value()).set(drivername="postgresql")
    with psycopg.connect(
        url.render_as_string(hide_password=False), connect_timeout=int(LIVE_TIMEOUT)
    ) as conn:
        row = conn.execute("SHOW server_version").fetchone()
    return f"PostgreSQL {row[0] if row else '?'}"


def _redis(settings: Settings, _env: Mapping[str, str]) -> str:
    client = redis.Redis.from_url(
        settings.redis_connection_url(),
        socket_timeout=LIVE_TIMEOUT,
        socket_connect_timeout=LIVE_TIMEOUT,
    )
    try:
        if not client.ping():
            message = "no PONG"
            raise ProbeError(message)
    finally:
        client.close()
    return "PONG with the password"


def _redis_persistence(settings: Settings, _env: Mapping[str, str]) -> str:
    """Prove that Redis keeps nothing on disk: a scanned photo waits there and must never reach it."""
    client = redis.Redis.from_url(
        settings.redis_connection_url(),
        socket_timeout=LIVE_TIMEOUT,
        socket_connect_timeout=LIVE_TIMEOUT,
        decode_responses=True,
    )
    try:
        appendonly = client.config_get("appendonly").get("appendonly")
        save = client.config_get("save").get("save")
    finally:
        client.close()
    if appendonly != "no" or save:
        message = f"appendonly={appendonly!r}, save={save!r}: photos in Redis would reach the disk"
        raise ProbeError(message)
    return "appendonly no, save empty"


def _ai_key(settings: Settings, _env: Mapping[str, str]) -> str:
    """List the provider's models with the key: it proves key and endpoint, and costs nothing."""
    provider = settings.ai
    resp = httpx.get(
        f"{provider.base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {provider.api_key.get_secret_value()}"},
        timeout=LIVE_TIMEOUT,
    )
    if resp.status_code in {401, 403}:
        message = (
            f"the {settings.ai_provider.value} endpoint refuses this key (HTTP {resp.status_code})"
        )
        raise ProbeError(message)
    resp.raise_for_status()
    return f"{_host(provider.base_url)} accepts the key"


def _detector(settings: Settings, _env: Mapping[str, str]) -> str:
    resp = httpx.get(f"{settings.detector_url.rstrip('/')}/health", timeout=LIVE_TIMEOUT)
    resp.raise_for_status()
    return f"{settings.detector_url} healthy"


def _smtp(settings: Settings, _env: Mapping[str, str]) -> str:
    """Connect, secure the connection and log in: no mail is sent."""
    timeout = settings.smtp_timeout_seconds
    context = ssl.create_default_context(cafile=settings.smtp_ca_file or None)
    server: smtplib.SMTP
    if settings.smtp_security == "ssl":
        server = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=timeout, context=context
        )
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
    with server:
        if settings.smtp_security == "starttls":
            server.starttls(context=context)
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
    return f"{settings.smtp_host}:{settings.smtp_port} accepts the login"


def _resolves(url: str) -> Callable[[Settings, Mapping[str, str]], str]:
    """Build the probe that this host resolves the name of URL (its own resolver, hosts file included)."""

    def probe(_settings: Settings, _env: Mapping[str, str]) -> str:
        host = _host(url)
        addresses = sorted(
            {str(info[4][0]) for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        )
        return f"{host} -> {', '.join(addresses)}"

    return probe


def _turnstile(settings: Settings, _env: Mapping[str, str]) -> str:
    """Post a dummy token: only the answer `invalid-input-secret` (a bad secret) is a failure."""

    async def ask() -> dict[str, Any] | None:
        try:
            return await turnstile_service.post_siteverify(
                settings.turnstile_secret_key.get_secret_value(), "tabsira-probe", None
            )
        finally:
            # The shared client belongs to this loop only; the next run makes its own.
            await turnstile_service.close_http_client()

    body = asyncio.run(ask())
    codes = body.get("error-codes") if body else None
    if not isinstance(codes, list):
        message = "Cloudflare gave no usable answer"
        raise ProbeError(message)
    if "invalid-input-secret" in codes:
        message = "Cloudflare refuses the secret as invalid"
        raise ProbeError(message)
    return "Cloudflare accepts the secret"


Probe = Callable[[Settings, Mapping[str, str]], str]


def live_probes(settings: Settings) -> list[tuple[str, str, Probe]]:
    """Return the services to try for real: what this deployment is configured to use."""
    table: list[tuple[bool, str, str, Probe]] = [
        (True, "Redis: PING with the password", REQUIRED, _redis),
        (True, "Redis: keeps nothing on disk", RECOMMENDED, _redis_persistence),
        (True, f"AI provider ({settings.ai_provider.value}): the key", REQUIRED, _ai_key),
        (True, "Detector: /health", RECOMMENDED, _detector),
        (settings.smtp_configured, "Mail: connect and log in", RECOMMENDED, _smtp),
        (
            settings.turnstile_enabled,
            "Turnstile: the secret",
            RECOMMENDED,
            _turnstile,
        ),
        (True, "DNS: the site", REQUIRED, _resolves(settings.site_url)),
        (True, "DNS: the API", REQUIRED, _resolves(settings.api_url)),
    ]
    return [(name, level, probe) for wanted, name, level, probe in table if wanted]


def live_checks(settings: Settings, env: Mapping[str, str]) -> list[Check]:
    """Try each service; a failure is reported with its reason, never raised."""
    checks = []
    for name, level, probe in live_probes(settings):
        try:
            checks.append(Check("Live", name, level, True, probe(settings, env)))
        except Exception as exc:  # every failure is reported, none raised
            checks.append(Check("Live", name, level, False, _short(exc)))
    return checks


# ─── Report ─────────────────────────────────────────────────────────

MARKS = {True: "ok     ", REQUIRED: "fix    ", RECOMMENDED: "check  ", OPTIONAL: "off    "}


def report_lines(checks: list[Check]) -> list[str]:
    """Return the checks as text, grouped by area, with a closing line."""
    lines: list[str] = []
    area = None
    for check in checks:
        if check.area != area:
            area = check.area
            lines.extend(["", area])
        mark = MARKS[True] if check.ok else MARKS[check.level]
        detail = f"  ({check.detail})" if check.detail else ""
        lines.append(f"  {mark} {check.name}{detail}")
    failed = sum(1 for c in checks if not c.ok and c.level == REQUIRED)
    warned = sum(1 for c in checks if not c.ok and c.level == RECOMMENDED)
    lines.append("")
    if failed:
        lines.append(f"{failed} required setting(s) missing or wrong.")
    else:
        lines.append(f"All required settings are in place. {warned} recommendation(s) to look at.")
    return lines


def has_failures(checks: list[Check]) -> bool:
    """Whether a required check failed: the deploy must stop."""
    return any(not c.ok and c.level == REQUIRED for c in checks)
