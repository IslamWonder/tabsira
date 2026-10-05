"""
Validate the configuration without starting the API.

    uv run python -m src.cli.check_config [--live] [--env-file PATH]

Exits 0 when the settings are valid, 1 when a key is missing or invalid. With
`--live` it also opens a connection to the database and runs `SELECT 1`.
Secrets are never printed: the report says whether a key is set, not its value.

With ENVIRONMENT=production it goes on to the production checklist
(src/cli/production_checks.py): every setting an operator reads before a
deploy, as ok / fix / check / off, and with `--live` each service tried for
real. A `fix` line stops the deploy: deploy/deploy.sh runs this before it
migrates.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import make_url

from src.cli import production_checks
from src.config import (
    ConfigError,
    Environment,
    Settings,
    checkout_root,
    format_validation_error,
    load_settings,
)
from src.storage.notice import storage_notice
from src.storage.probe import StorageProbeError, probe_storage


def _database_label(source: SecretStr) -> str:
    """Return host, port and name of the database, without its credentials."""
    url = make_url(source.get_secret_value())
    return f"{url.host}:{url.port or 5432}/{url.database}"


def _queried_url(settings: Settings) -> SecretStr:
    """Return the URL the live check queries: the sync one when set."""
    return settings.sync_database_url or settings.database_url


def _psycopg_dsn(settings: Settings) -> str:
    """Return a libpq URL for the database, preferring the sync URL when set."""
    return (
        make_url(_queried_url(settings).get_secret_value())
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def _check_database(settings: Settings) -> str | None:
    """Return a problem description when the database cannot be queried, else None."""
    try:
        with (
            psycopg.connect(
                _psycopg_dsn(settings), connect_timeout=max(1, int(settings.db_connect_timeout))
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT 1")
    except psycopg.Error as error:
        return f"cannot query {_database_label(_queried_url(settings))}: {type(error).__name__}"
    return None


def report(settings: Settings) -> list[str]:
    """Return the lines that describe a valid configuration."""
    flags = sorted(name for name in Settings.model_fields if name.startswith("feature_"))
    on = [name.removeprefix("feature_") for name in flags if getattr(settings, name)]
    key_state = "set" if settings.ai.api_key.get_secret_value() else "NOT set"
    lines = [
        f"environment: {settings.environment.value}",
        f"api: {settings.api_host}:{settings.api_port} (public {settings.api_url})",
        f"site: {settings.site_url}",
        f"database: {_database_label(settings.database_url)}",
        f"test database: {'set' if settings.test_database_url else 'not set'}",
        f"ai provider: {settings.ai_provider.value} (api key {key_state})",
        f"features on: {', '.join(on) or 'none'}",
        f"photos: {settings.resolved_storage_backend}",
    ]
    notice = storage_notice(settings)
    if notice is not None:
        lines.append(f"WARNING: {notice}")
    return lines


def storage_report(settings: Settings) -> tuple[str, bool]:
    """
    Probe the photo storage; return the line to print and whether the check passed.

    A failure fails the check in production only: elsewhere it is a warning, as at start.
    """
    try:
        probe_storage(settings)
    except StorageProbeError as error:
        return f"storage: FAILED, {error}", settings.environment != Environment.PRODUCTION
    return "storage: ok", True


def _load(env_file: Path | None) -> Settings:
    """Read the settings, from `env_file` when one is named; raise `ConfigError` naming bad keys."""
    if env_file is None:
        return load_settings()
    try:
        return Settings(_env_file=env_file)
    except ValidationError as error:
        raise ConfigError(format_validation_error(error)) from None


def production_report(settings: Settings, env_file: Path | None, *, live: bool) -> bool:
    """Print the production checklist; return whether every required line passed."""
    path = env_file or checkout_root() / ".env"
    env = {k: v or "" for k, v in dotenv_values(path).items()} if path.is_file() else {}
    checks = production_checks.run_checks(settings, env)
    if live:
        checks += production_checks.live_checks(settings, env)
    sys.stdout.write("\n".join(production_checks.report_lines(checks)) + "\n")
    return not production_checks.has_failures(checks)


def main(argv: Sequence[str] | None = None) -> int:
    """Check the configuration; return the process exit code."""
    parser = argparse.ArgumentParser(description="Validate the TABSIRA API configuration.")
    parser.add_argument("--live", action="store_true", help="also try the services for real")
    parser.add_argument("--env-file", type=Path, default=None, help="the environment file to check")
    args = parser.parse_args(argv)

    try:
        settings = _load(args.env_file)
    except ConfigError as error:
        sys.stderr.write(f"{error}\n")
        return 1

    sys.stdout.write("Configuration is valid.\n")
    for line in report(settings):
        sys.stdout.write(f"  {line}\n")

    line, storage_ok = storage_report(settings)
    if not storage_ok:
        sys.stderr.write(f"{line}\n")
        return 1
    sys.stdout.write(f"  {line}\n")

    if args.live:
        problem = _check_database(settings)
        if problem:
            sys.stderr.write(f"Database check failed: {problem}\n")
            return 1
        sys.stdout.write("  database: reachable\n")
    if settings.environment == Environment.PRODUCTION and not production_report(
        settings, args.env_file, live=args.live
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
