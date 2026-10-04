from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from src.cli import check_config

API_DIR = Path(__file__).resolve().parents[1]
PASSWORD = "s3cr3t-pw"


@pytest.fixture(autouse=True)
def no_cli_arguments(monkeypatch):
    """`main()` parses sys.argv; pytest's own arguments must not reach it."""
    monkeypatch.setattr(sys, "argv", ["check_config"])


def test_a_valid_configuration_is_reported_without_secrets(monkeypatch, capsys):
    monkeypatch.setenv(
        "DATABASE_URL", f"postgresql+asyncpg://tabsira:{PASSWORD}@127.0.0.1:5432/tabsira"
    )
    monkeypatch.setenv("AI_OPENAI__API_KEY", "openai-secret-key")

    code = check_config.main([])

    out = capsys.readouterr()
    assert code == 0
    assert "Configuration is valid." in out.out
    assert "environment: test" in out.out
    assert "database: 127.0.0.1:5432/tabsira" in out.out
    assert "test database: not set" in out.out
    assert "ai provider: openai (api key set)" in out.out
    assert (
        "features on: admin, atlas, camera_discovery, canonical_verify, chat, "
        "photo_storage, social, treasure, world"
    ) in out.out
    assert "camera_anchor" not in out.out
    assert out.err == ""
    assert PASSWORD not in out.out + out.err
    assert "openai-secret-key" not in out.out + out.err


def test_the_report_marks_a_missing_key_and_a_set_test_database(monkeypatch, capsys):
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql+asyncpg://tabsira:pw@127.0.0.1/tabsira_test"
    )
    for name in check_config.Settings.model_fields:
        if name.startswith("feature_"):
            monkeypatch.setenv(name.upper(), "false")

    assert check_config.main([]) == 0

    out = capsys.readouterr().out
    assert "ai provider: openai (api key NOT set)" in out
    assert "test database: set" in out
    assert "features on: none" in out


def test_an_invalid_configuration_exits_one_and_names_the_key(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.setenv("API_PORT", "nope")

    code = check_config.main([])

    out = capsys.readouterr()
    assert code == 1
    assert out.out == ""
    assert "DATABASE_URL: Field required" in out.err
    assert "API_PORT" in out.err


def test_main_reads_its_arguments_from_the_command_line_by_default(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["check_config"])

    assert check_config.main() == 0
    assert "Configuration is valid." in capsys.readouterr().out


class FakeConnection:
    def __init__(self, fail: bool, dsns: list[str]) -> None:
        self.fail = fail
        self.dsns = dsns

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def cursor(self):
        return self

    def execute(self, query):
        self.dsns.append(query)
        if self.fail:
            raise psycopg.OperationalError("password=hunter2")


def patch_psycopg(monkeypatch, *, fail: bool = False, connect_error: bool = False):
    seen: list = []

    def connect(dsn, **kwargs):
        seen.append((dsn, kwargs))
        if connect_error:
            raise psycopg.OperationalError("connection refused, password=hunter2")
        return FakeConnection(fail, seen)

    monkeypatch.setattr(check_config.psycopg, "connect", connect)
    return seen


def test_live_check_queries_the_database_over_psycopg(monkeypatch, capsys):
    seen = patch_psycopg(monkeypatch)

    code = check_config.main(["--live"])

    assert code == 0
    assert "database: reachable" in capsys.readouterr().out
    dsn, kwargs = seen[0]
    assert dsn.startswith("postgresql://")
    assert "+asyncpg" not in dsn
    assert kwargs == {"connect_timeout": 3}
    assert seen[1] == "SELECT 1"


def test_live_check_prefers_the_sync_database_url(monkeypatch):
    monkeypatch.setenv("SYNC_DATABASE_URL", "postgresql+psycopg://sync:pw@127.0.0.1:5433/other")
    seen = patch_psycopg(monkeypatch)

    assert check_config.main(["--live"]) == 0

    assert seen[0][0] == "postgresql://sync:pw@127.0.0.1:5433/other"


@pytest.mark.parametrize("variant", [{"connect_error": True}, {"fail": True}])
def test_live_check_failure_exits_one_without_leaking_the_error_text(monkeypatch, capsys, variant):
    # Pin the address: CI runs its database on a port chosen per build.
    monkeypatch.setenv(
        "SYNC_DATABASE_URL", f"postgresql+psycopg://tabsira:{PASSWORD}@127.0.0.1:5432/tabsira"
    )
    patch_psycopg(monkeypatch, **variant)

    code = check_config.main(["--live"])

    out = capsys.readouterr()
    assert code == 1
    assert "Database check failed: cannot query 127.0.0.1:5432/" in out.err
    assert "OperationalError" in out.err
    assert "hunter2" not in out.out + out.err


def test_the_connect_timeout_is_at_least_one_second(monkeypatch):
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "0.2")
    seen = patch_psycopg(monkeypatch)

    check_config.main(["--live"])

    assert seen[0][1] == {"connect_timeout": 1}


def test_running_the_module_exits_non_zero_when_the_configuration_is_invalid(monkeypatch):
    env = {k: v for k, v in __import__("os").environ.items() if k != "DATABASE_URL"}

    result = subprocess.run(
        [sys.executable, "-m", "src.cli.check_config"],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "DATABASE_URL: Field required" in result.stderr
