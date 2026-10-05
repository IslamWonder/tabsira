from __future__ import annotations

import smtplib
import socket
import sys
from pathlib import Path

import httpx
import psycopg
import pytest
import redis
from dotenv import dotenv_values

from src.cli import check_config, production_checks
from src.cli.production_checks import Check
from src.config import Settings
from src.services import turnstile_service

FERNET_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
DATABASE_URL = "postgresql+asyncpg://tabsira:a-long-database-password@10.0.0.2:5432/tabsira"
SYNC_URL = "postgresql+psycopg://tabsira:a-long-database-password@10.0.0.2:5432/tabsira"
PRODUCTION = {
    "environment": "production",
    "database_url": DATABASE_URL,
    "sync_database_url": SYNC_URL,
    "site_url": "https://tabsira.me",
    "api_url": "https://api.tabsira.me",
    "admin_url": "https://admin.tabsira.me",
    "cors_origins": "https://tabsira.me",
    "session_cookie_domain": ".tabsira.me",
    "hash_secret": "not-a-real-secret-but-long-enough-for-the-rule",
    "ai_provider": "openai",
    "ai_openai": {"api_key": "openai-key-123"},
    "admin_totp_encryption_key": FERNET_KEY,
    "redis_password": "a-long-redis-password",
    "s3_bucket": "tabsira-photos",
    "s3_access_key_id": "AKIAEXAMPLE",
    "s3_secret_access_key": "s3-secret-value",
    "s3_public_base_url": "https://media.tabsira.me",
    "smtp_host": "smtp.example.com",
    "smtp_username": "mailer",
    "smtp_password": "mailer-password",
    "mail_from": "تبصرة <no-reply@tabsira.me>",
    "support_email": "support@tabsira.me",
    "privacy_email": "privacy@tabsira.me",
    "glitchtip_dsn": "https://key@errors.example.com/1",
    "admin_require_two_factor": True,
    "geo_approx_cell_meters": 1000,
}
# A complete file: every key of the production example with its example value, the
# placeholders filled, as the owners' file is; the checklist requires every key present.
EXAMPLE_KEYS = production_checks.example_keys() or set()
ENV = {
    **{
        key: value.replace("CHANGE_ME", "filled").replace("_VPN_IP", "")
        for key, value in dotenv_values(production_checks.EXAMPLE_FILE).items()
        for value in [value or ""]
    },
    "API_WORKERS": "3",
    "WEB_INSTANCES": "2",
    "WEB_PORT": "3000",
    "GA_MEASUREMENT_ID": "G-ABCDEF1234",
}


def settings_of(**changes: object) -> Settings:
    return Settings(_env_file=None, **{**PRODUCTION, **changes})  # type: ignore[arg-type]


def by_name(checks: list[Check]) -> dict[str, Check]:
    return {c.name: c for c in checks}


def failing(checks: list[Check], level: str | None = None) -> list[str]:
    return [c.name for c in checks if not c.ok and (level is None or c.level == level)]


def test_a_complete_production_file_has_no_required_line_to_fix():
    checks = production_checks.run_checks(settings_of(), ENV)

    assert failing(checks, production_checks.REQUIRED) == []
    assert not production_checks.has_failures(checks)


def test_the_file_mirrors_the_example_key_for_key():
    assert len(EXAMPLE_KEYS) > 100
    missing_two = {k: v for k, v in ENV.items() if k not in {"API_WORKERS", "GLITCHTIP_DSN"}}
    checks = by_name(production_checks.run_checks(settings_of(), missing_two))
    line = checks["every key of deploy/env.production.example is in the file"]
    assert (line.level, line.ok, line.detail) == (
        production_checks.REQUIRED,
        False,
        "API_WORKERS, GLITCHTIP_DSN",
    )

    checks = by_name(production_checks.run_checks(settings_of(), {**ENV, "AI_PROVDER": "openai"}))
    line = checks["no key the example does not know"]
    assert (line.level, line.ok, line.detail) == (
        production_checks.RECOMMENDED,
        False,
        "AI_PROVDER",
    )
    assert checks["every key of deploy/env.production.example is in the file"].ok


def test_a_file_cannot_be_compared_when_the_example_is_not_beside_the_code(monkeypatch, tmp_path):
    monkeypatch.setattr(production_checks, "EXAMPLE_FILE", tmp_path / "missing.example")
    checks = by_name(production_checks.run_checks(settings_of(), {}))

    line = checks["deploy/env.production.example is beside the code"]
    assert (line.level, line.ok) == (production_checks.RECOMMENDED, False)
    assert "every key of deploy/env.production.example is in the file" not in checks


def test_a_placeholder_left_in_the_file_is_named_without_its_value():
    env = {**ENV, "REDIS_PASSWORD": "CHANGE_ME", "DATABASE_URL": "x@DATA_HOST_VPN_IP:5432"}

    check = by_name(production_checks.run_checks(settings_of(), env))[
        "no placeholder left in the file"
    ]

    assert not check.ok
    assert check.detail == "DATABASE_URL, REDIS_PASSWORD"


def test_the_public_names_must_share_one_domain_and_the_cookie_must_cover_them():
    checks = by_name(
        production_checks.run_checks(
            settings_of(api_url="https://api.other.me", session_cookie_domain=".other.me"), ENV
        )
    )

    assert not checks["SITE_URL / API_URL / ADMIN_URL share one domain"].ok
    assert not checks["SESSION_COOKIE_DOMAIN covers the site and the API"].ok


def test_cors_must_hold_the_site_and_nothing_else():
    checks = by_name(
        production_checks.run_checks(
            settings_of(cors_origins="https://tabsira.me,https://other.me"), ENV
        )
    )

    assert not checks["CORS_ORIGINS holds the site and nothing else"].ok


def test_the_api_must_listen_on_loopback():
    checks = by_name(production_checks.run_checks(settings_of(api_host="0.0.0.0"), ENV))  # noqa: S104

    assert not checks["API_HOST is loopback"].ok


def test_recommendations_are_reported_as_such_not_as_required():
    checks = production_checks.run_checks(
        settings_of(
            admin_require_two_factor=False,
            enabled_features="camera_anchor",
            geo_approx_cell_meters=500,
            glitchtip_dsn="",
            detector_url="http://10.0.0.9:8100",
            mail_from="no-reply@other.me",
            support_email="help@other.me",
        ),
        ENV,
    )

    assert failing(checks, production_checks.REQUIRED) == []
    assert set(failing(checks, production_checks.RECOMMENDED)) >= {
        "ADMIN_REQUIRE_TWO_FACTOR=true",
        "camera_anchor is not in ENABLED_FEATURES",
        "GEO_APPROX_CELL_METERS is at least 1000",
        "GLITCHTIP_DSN",
        "DETECTOR_URL is loopback",
        "MAIL_FROM is on the site's domain",
        "SUPPORT_EMAIL is on the site's domain",
    }


def test_a_database_url_apart_from_the_sync_one_is_a_required_fix():
    other = "postgresql+psycopg://tabsira:a-long-database-password@10.0.0.3:5432/tabsira"
    checks = by_name(production_checks.run_checks(settings_of(sync_database_url=other), ENV))
    missing = by_name(production_checks.run_checks(settings_of(sync_database_url=None), ENV))

    assert not checks["SYNC_DATABASE_URL names the same database"].ok
    assert not missing["SYNC_DATABASE_URL names the same database"].ok


def test_short_passwords_and_a_pool_that_overflows_are_flagged():
    short = "postgresql+asyncpg://tabsira:short@10.0.0.2:5432/tabsira"
    checks = by_name(
        production_checks.run_checks(
            settings_of(database_url=short, sync_database_url=None, redis_password="short"),
            {**ENV, "API_WORKERS": "12"},
        )
    )

    assert not checks["database password is long"].ok
    assert not checks["REDIS_PASSWORD is long"].ok
    assert not checks["database connections fit under max_connections"].ok


@pytest.mark.parametrize("workers", ["0", "many", "-1"])
def test_api_workers_must_be_a_positive_number(workers):
    checks = by_name(production_checks.run_checks(settings_of(), {**ENV, "API_WORKERS": workers}))

    assert not checks["API_WORKERS is a positive number"].ok
    assert "database connections fit under max_connections" not in checks


def test_an_empty_api_workers_means_the_default():
    checks = by_name(production_checks.run_checks(settings_of(), {"WEB_PORT": ""}))

    assert checks["API_WORKERS is a positive number"].ok


def test_a_blank_model_line_is_a_required_fix_because_it_overrides_the_default():
    checks = by_name(
        production_checks.run_checks(
            settings_of(ai_openai={"api_key": "k", "planner_model": ""}), ENV
        )
    )

    stage = checks["every stage has a model (openai)"]
    assert not stage.ok
    assert stage.detail == "no model for: planner"


def test_the_rerank_model_matters_only_when_reranking_uses_a_model():
    off = settings_of(ai_openai={"api_key": "k", "rerank_model": ""})
    llm = settings_of(ai_openai={"api_key": "k", "rerank_model": ""}, reranker="llm")

    assert by_name(production_checks.run_checks(off, ENV))["every stage has a model (openai)"].ok
    assert not by_name(production_checks.run_checks(llm, ENV))[
        "every stage has a model (openai)"
    ].ok


def test_the_guard_model_is_recommended():
    settings = settings_of(ai_provider="ovh", ai_ovh={"api_key": "k"})

    check = by_name(production_checks.run_checks(settings, ENV))["the content guard has a model"]

    assert not check.ok
    assert check.level == production_checks.RECOMMENDED


def test_mail_is_required_and_the_sender_must_be_on_the_site_domain():
    checks = by_name(production_checks.run_checks(settings_of(smtp_host=""), ENV))

    assert not checks["SMTP_HOST is set"].ok
    assert checks["SMTP_HOST is set"].level == production_checks.REQUIRED


def test_photos_are_kept_in_s3(make_settings):
    checks = by_name(production_checks.run_checks(settings_of(), ENV))

    assert checks["STORAGE_BACKEND resolves to s3"].ok


def test_google_sign_in_is_optional_until_configured_then_its_callback_is_checked():
    off = by_name(production_checks.run_checks(settings_of(), ENV))
    on = production_checks.run_checks(
        settings_of(
            google_client_id="id.apps.googleusercontent.com",
            google_client_secret="secret",
            google_redirect_uri="https://api.tabsira.me/auth/google/callback",
        ),
        ENV,
    )
    wrong = production_checks.run_checks(
        settings_of(
            google_client_id="id.apps.googleusercontent.com",
            google_client_secret="secret",
            google_redirect_uri="https://tabsira.me/auth/google/callback",
        ),
        ENV,
    )

    assert off["Google"].level == production_checks.OPTIONAL
    assert by_name(on)["GOOGLE_REDIRECT_URI"].ok
    assert not by_name(wrong)["GOOGLE_REDIRECT_URI"].ok


def test_the_baked_web_addresses_must_match_the_server_ones_when_set():
    wrong = {
        **ENV,
        "NEXT_PUBLIC_SITE_URL": "https://tabsira.test",
        "NEXT_PUBLIC_API_URL": "https://api.tabsira.me/",
    }
    checks = by_name(production_checks.run_checks(settings_of(), wrong))

    assert not checks["NEXT_PUBLIC_SITE_URL"].ok
    assert checks["NEXT_PUBLIC_API_URL"].ok
    assert by_name(production_checks.run_checks(settings_of(), ENV))["NEXT_PUBLIC_SITE_URL"].ok


@pytest.mark.parametrize(
    ("env", "ok"),
    [
        ({"WEB_INSTANCES": "max", "WEB_PORT": "3000"}, True),
        ({"WEB_INSTANCES": "", "WEB_PORT": ""}, True),
        ({"WEB_INSTANCES": "two"}, False),
        ({"WEB_PORT": "port"}, False),
    ],
)
def test_the_pm2_instances_and_port_must_be_usable(env, ok):
    check = by_name(production_checks.run_checks(settings_of(), env))["WEB_INSTANCES / WEB_PORT"]

    assert check.ok is ok


def test_analytics_ids_are_optional_and_the_google_one_must_look_right():
    empty = by_name(production_checks.run_checks(settings_of(), {}))
    bad = by_name(production_checks.run_checks(settings_of(), {"GA_MEASUREMENT_ID": "UA-1"}))
    good = by_name(production_checks.run_checks(settings_of(), ENV))

    assert empty["GA_MEASUREMENT_ID"].level == production_checks.OPTIONAL
    assert not bad["GA_MEASUREMENT_ID"].ok
    assert good["GA_MEASUREMENT_ID"].ok
    assert not empty["CLARITY_PROJECT_ID"].ok


# ─── Live probes ────────────────────────────────────────────────────


class FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)  # type: ignore[arg-type]


class FakeRedis:
    def __init__(self, ping: bool = True, appendonly: str = "no", save: str = "") -> None:
        self._ping, self._config = ping, {"appendonly": appendonly, "save": save}
        self.closed = False

    def ping(self) -> bool:
        return self._ping

    def config_get(self, name: str) -> dict[str, str]:
        return {name: self._config[name]}

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def cursor(self):
        return self

    def execute(self, _query):
        return self

    def fetchone(self):
        return ("18.1",)


class FakeSmtp:
    log: list[str] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.log = [f"connect {host}:{port}"]
        FakeSmtp.log = self.log
        self.context = context

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def starttls(self, context):
        self.log.append("starttls")

    def login(self, user, password):
        self.log.append(f"login {user}")


@pytest.fixture
def live_world(monkeypatch):
    monkeypatch.setattr(psycopg, "connect", lambda *_a, **_k: FakeConnection())
    monkeypatch.setattr(redis.Redis, "from_url", lambda *_a, **_k: FakeRedis())
    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: FakeResponse())
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *_a, **_k: [(2, 1, 6, "", ("203.0.113.7", 443))]
    )


def live(settings=None) -> dict[str, Check]:
    return by_name(production_checks.live_checks(settings or settings_of(), ENV))


def test_every_service_is_tried_and_reported_when_all_answer(live_world):
    checks = live()

    assert all(c.ok for c in checks.values()), [c for c in checks.values() if not c.ok]
    assert checks["Redis: PING with the password"].detail == "PONG with the password"
    assert checks["Redis: keeps nothing on disk"].detail == "appendonly no, save empty"
    assert checks["DNS: the site"].detail == "tabsira.me -> 203.0.113.7"
    assert checks["AI provider (openai): the key"].detail == "api.openai.com accepts the key"
    assert "Mail: connect and log in" in checks


def test_the_database_is_tried_by_the_existing_check_not_the_checklist(live_world):
    assert "Database: connect" not in live()


def test_a_redis_that_keeps_data_on_disk_is_flagged(live_world, monkeypatch):
    monkeypatch.setattr(
        redis.Redis, "from_url", lambda *_a, **_k: FakeRedis(appendonly="yes", save="3600 1")
    )

    check = live()["Redis: keeps nothing on disk"]

    assert not check.ok
    assert "photos in Redis would reach the disk" in check.detail


def test_a_redis_that_does_not_pong_is_a_required_fix(live_world, monkeypatch):
    monkeypatch.setattr(redis.Redis, "from_url", lambda *_a, **_k: FakeRedis(ping=False))

    check = live()["Redis: PING with the password"]

    assert not check.ok
    assert check.level == production_checks.REQUIRED


def test_a_refused_ai_key_is_a_required_fix_without_the_key_in_the_report(live_world, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: FakeResponse(401))

    check = live()["AI provider (openai): the key"]

    assert not check.ok
    assert "refuses this key (HTTP 401)" in check.detail
    assert "openai-key-123" not in check.detail


def test_a_failing_service_is_reported_not_raised(live_world, monkeypatch):
    def refuse(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr(
        httpx, "get", lambda url, **_k: refuse() if "8100" in url else FakeResponse()
    )

    check = live()["Detector: /health"]

    assert not check.ok
    assert check.detail == "connection refused"


def test_a_name_that_does_not_resolve_is_a_required_fix(live_world, monkeypatch):
    def fail(*_a, **_k):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", fail)

    check = live()["DNS: the API"]

    assert not check.ok
    assert check.level == production_checks.REQUIRED


@pytest.mark.parametrize(
    ("security", "steps"), [("starttls", ["starttls", "login mailer"]), ("ssl", ["login mailer"])]
)
def test_mail_is_tried_by_logging_in_never_by_sending(live_world, security, steps):
    check = live(settings_of(smtp_security=security))["Mail: connect and log in"]

    assert check.ok
    assert FakeSmtp.log[1:] == steps


def test_mail_without_a_login_only_connects(live_world):
    live(settings_of(smtp_username="", smtp_password=""))

    assert FakeSmtp.log == ["connect smtp.example.com:587", "starttls"]


def test_mail_is_not_tried_when_it_is_not_configured(live_world):
    assert "Mail: connect and log in" not in live(settings_of(smtp_host=""))


def test_the_database_probe_asks_for_the_version_over_the_sync_url(monkeypatch):
    seen: list[str] = []

    def connect(dsn, **_kwargs):
        seen.append(dsn)
        return FakeConnection()

    monkeypatch.setattr(psycopg, "connect", connect)

    assert production_checks._database(settings_of(), ENV) == "PostgreSQL 18.1"
    assert seen[0].startswith("postgresql://tabsira:a-long-database-password@10.0.0.2")


def test_the_database_probe_falls_back_to_the_async_url(monkeypatch):
    monkeypatch.setattr(psycopg, "connect", lambda *_a, **_k: FakeConnection())

    assert (
        production_checks._database(settings_of(sync_database_url=None), ENV) == "PostgreSQL 18.1"
    )


# ─── Report ─────────────────────────────────────────────────────────


def test_the_report_groups_by_area_and_marks_each_level():
    checks = [
        Check("API", "a", production_checks.REQUIRED, True),
        Check("API", "b", production_checks.REQUIRED, False, "why"),
        Check("Web", "c", production_checks.RECOMMENDED, False),
        Check("Web", "d", production_checks.OPTIONAL, False, "off for now"),
    ]

    lines = production_checks.report_lines(checks)

    assert lines == [
        "",
        "API",
        "  ok      a",
        "  fix     b  (why)",
        "",
        "Web",
        "  check   c",
        "  off     d  (off for now)",
        "",
        "1 required setting(s) missing or wrong.",
    ]
    assert production_checks.has_failures(checks)


def test_the_report_closes_with_the_count_of_recommendations_when_nothing_is_required():
    checks = [Check("Web", "c", production_checks.RECOMMENDED, False)]

    assert production_checks.report_lines(checks)[-1] == (
        "All required settings are in place. 1 recommendation(s) to look at."
    )


# ─── check_config in production ─────────────────────────────────────


@pytest.fixture
def production_env(monkeypatch, tmp_path):
    """A production environment file on disk, and the process pointed at it."""
    lines = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": DATABASE_URL,
        "SYNC_DATABASE_URL": SYNC_URL,
        "SITE_URL": "https://tabsira.me",
        "API_URL": "https://api.tabsira.me",
        "ADMIN_URL": "https://admin.tabsira.me",
        "CORS_ORIGINS": "https://tabsira.me",
        "SESSION_COOKIE_DOMAIN": ".tabsira.me",
        "HASH_SECRET": "not-a-real-secret-but-long-enough-for-the-rule",
        "AI_OPENAI__API_KEY": "openai-key-123",
        "ADMIN_TOTP_ENCRYPTION_KEY": FERNET_KEY,
        "REDIS_PASSWORD": "a-long-redis-password",
        "STORAGE_BACKEND": "s3",
        "S3_BUCKET": "tabsira-photos",
        "S3_ACCESS_KEY_ID": "AKIAEXAMPLE",
        "S3_SECRET_ACCESS_KEY": "s3-secret-value",
        "S3_PUBLIC_BASE_URL": "https://media.tabsira.me",
        "SMTP_HOST": "smtp.example.com",
        "GOOGLE_REDIRECT_URI": "https://api.tabsira.me/auth/google/callback",
        "API_WORKERS": "3",
    }
    # On top of the complete example, as the owners' file is; the checklist wants every key.
    lines = {**ENV, **lines}
    assert all("'" not in v for v in lines.values())
    path = tmp_path / "production.env"
    path.write_text("\n".join(f"{k}='{v}'" for k, v in lines.items()) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_config"])
    # The suite's own environment (ENVIRONMENT=test, development URLs) outranks the
    # file; a deploy has no such variables, so the file's values are set over them.
    for key, value in lines.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("LOCAL_MEDIA_DIR", raising=False)
    monkeypatch.setattr(check_config, "probe_storage", lambda _settings: None)
    return path


def test_check_config_prints_the_production_checklist_and_exits_zero(production_env, capsys):
    code = check_config.main(["--env-file", str(production_env)])

    out = capsys.readouterr().out
    assert code == 0, out
    assert "environment: production" in out
    assert "  ok      API_HOST is loopback" in out
    assert "All required settings are in place." in out
    assert "a-long-redis-password" not in out
    assert "openai-key-123" not in out


def test_check_config_exits_one_when_a_required_line_fails(production_env, capsys):
    production_env.write_text(
        production_env.read_text(encoding="utf-8").replace("API_WORKERS='3'", "API_WORKERS='zero'"),
        encoding="utf-8",
    )

    code = check_config.main(["--env-file", str(production_env)])

    out = capsys.readouterr().out
    assert code == 1
    assert "  fix     API_WORKERS is a positive number" in out
    assert "1 required setting(s) missing or wrong." in out


def test_check_config_tries_the_services_with_live(production_env, live_world, capsys):
    code = check_config.main(["--env-file", str(production_env), "--live"])

    out = capsys.readouterr().out
    assert code == 0
    assert "database: reachable" in out
    assert "  ok      Redis: PING with the password" in out


def test_check_config_reports_a_bad_env_file_by_key(tmp_path, capsys):
    bad = tmp_path / "bad.env"
    bad.write_text("API_PORT=nope\n", encoding="utf-8")

    code = check_config.main(["--env-file", str(bad)])

    assert code == 1
    assert "API_PORT" in capsys.readouterr().err


def test_production_report_treats_a_missing_file_as_every_key_missing(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(check_config, "checkout_root", lambda: Path(tmp_path))

    ok = check_config.production_report(settings_of(), None, live=False)

    out = capsys.readouterr().out
    assert not ok
    assert "  fix     every key of deploy/env.production.example is in the file" in out


# ─── Turnstile ──────────────────────────────────────────────────────

TURNSTILE = {
    "turnstile_site_key": "0x4AAAAAAAexample-key",
    "turnstile_secret_key": "0x4AAAAAAAsecretvalue",
}
TURNSTILE_LINE = "TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY"


def test_turnstile_is_a_recommendation_met_when_both_keys_are_set():
    off = by_name(production_checks.run_checks(settings_of(), ENV))[TURNSTILE_LINE]
    on = by_name(production_checks.run_checks(settings_of(**TURNSTILE), ENV))[TURNSTILE_LINE]

    assert not off.ok
    assert off.level == production_checks.RECOMMENDED
    assert on.ok


def fake_cloudflare(monkeypatch, body):
    asked: list[tuple[str, str, str | None]] = []

    async def post(secret, token, remote_ip):
        asked.append((secret, token, remote_ip))
        return body

    monkeypatch.setattr(turnstile_service, "post_siteverify", post)
    return asked


def test_the_secret_is_not_probed_when_turnstile_is_off(live_world):
    assert "Turnstile: the secret" not in live()


def test_a_good_secret_is_told_the_dummy_token_is_invalid(live_world, monkeypatch):
    asked = fake_cloudflare(
        monkeypatch, {"success": False, "error-codes": ["invalid-input-response"]}
    )

    check = live(settings_of(**TURNSTILE))["Turnstile: the secret"]

    assert check.ok
    assert check.level == production_checks.RECOMMENDED
    assert asked == [(TURNSTILE["turnstile_secret_key"], "tabsira-probe", None)]
    assert TURNSTILE["turnstile_secret_key"] not in check.detail


def test_a_bad_secret_fails_without_printing_it(live_world, monkeypatch):
    fake_cloudflare(monkeypatch, {"success": False, "error-codes": ["invalid-input-secret"]})

    check = live(settings_of(**TURNSTILE))["Turnstile: the secret"]

    assert not check.ok
    assert TURNSTILE["turnstile_secret_key"] not in check.detail


@pytest.mark.parametrize("body", [None, {"success": False}, {"error-codes": "x"}])
def test_no_usable_answer_from_cloudflare_is_reported(live_world, monkeypatch, body):
    fake_cloudflare(monkeypatch, body)

    check = live(settings_of(**TURNSTILE))["Turnstile: the secret"]

    assert not check.ok
    assert check.detail == "Cloudflare gave no usable answer"
