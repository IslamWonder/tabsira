"""The root .env.example and the typed settings must never drift apart."""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import dotenv_values
from pydantic import SecretStr, ValidationError

from src.config import AiStage, ProviderSettings, Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = REPO_ROOT / ".env.example"
API_HEADING = "# ==== API (apps/api) ===="
SECRETS = {
    "DATABASE_URL",
    "SYNC_DATABASE_URL",
    "TEST_DATABASE_URL",
    "AI_OVH__API_KEY",
    "AI_OPENAI__API_KEY",
    "HASH_SECRET",
    "GOOGLE_CLIENT_SECRET",
    "SMTP_PASSWORD",
    "GLITCHTIP_DSN",
    "GLITCHTIP_WEB_DSN",
    "S3_SECRET_ACCESS_KEY",
    "ADMIN_TOTP_ENCRYPTION_KEY",
}


def settings_keys() -> set[str]:
    """Every environment variable the settings read, nested blocks flattened."""
    keys = set()
    for name, field in Settings.model_fields.items():
        if isinstance(field.default, ProviderSettings):
            keys |= {f"{name}__{sub}".upper() for sub in type(field.default).model_fields}
        else:
            keys.add(name.upper())
    return keys


def api_section_keys() -> list[str]:
    """The keys of the API section: from its heading to the next section heading, or the end."""
    keys: list[str] = []
    in_section = False
    for line in EXAMPLE.read_text().splitlines():
        if line.startswith("# ===="):
            in_section = line == API_HEADING
        elif in_section and line and not line.startswith("#"):
            keys.append(line.split("=", 1)[0])
    return keys


def test_every_setting_is_listed_once_and_nothing_else_is_in_the_api_section():
    listed = api_section_keys()

    assert len(listed) == len(set(listed)), "a key appears twice"
    assert set(listed) == settings_keys()


def test_every_key_is_documented_by_the_line_above_it():
    lines = EXAMPLE.read_text().splitlines()
    for index, line in enumerate(lines):
        if line and not line.startswith("#"):
            assert lines[index - 1].startswith("# "), f"{line.split('=')[0]} has no comment"


def test_secrets_are_empty():
    values = dotenv_values(EXAMPLE)

    assert {key for key in SECRETS if values[key]} == set()


def test_provider_blocks_name_one_model_per_stage():
    assert {
        f"AI_{block}__{stage.value.upper()}_MODEL"
        for block in ("OVH", "OPENAI")
        for stage in AiStage
    } <= (settings_keys())


def test_the_development_defaults_in_the_file_are_the_defaults_in_the_code(
    make_settings, monkeypatch
):
    for key in ("ENVIRONMENT",):
        monkeypatch.delenv(key)

    from_file = Settings(_env_file=EXAMPLE, database_url="postgresql+asyncpg://u:p@127.0.0.1/db")
    from_code = make_settings(database_url="postgresql+asyncpg://u:p@127.0.0.1/db")

    assert from_file.model_dump() == from_code.model_dump()


def test_an_untouched_copy_names_the_one_key_the_developer_must_fill_in(monkeypatch):
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=EXAMPLE)

    assert [error["loc"] for error in caught.value.errors()] == [("database_url",)]


def test_every_secret_setting_is_known_to_this_test_so_none_is_shipped_filled():
    secret_types = (SecretStr, SecretStr | None)
    top_level = {
        name.upper()
        for name, field in Settings.model_fields.items()
        if field.annotation in secret_types
    }
    nested = {
        f"{name}__{sub}".upper()
        for name, field in Settings.model_fields.items()
        if isinstance(field.default, ProviderSettings)
        for sub, sub_field in type(field.default).model_fields.items()
        if sub_field.annotation is SecretStr
    }

    assert top_level | nested == SECRETS
