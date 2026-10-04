from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src import config
from src.config import (
    AiProvider,
    AiStage,
    ConfigError,
    Environment,
    Settings,
    format_validation_error,
    get_settings,
    load_settings,
)

PASSWORD = "s3cr3t-pw"
DATABASE_URL = f"postgresql+asyncpg://tabsira:{PASSWORD}@127.0.0.1:5432/tabsira"
SYNC_URL = f"postgresql+psycopg://tabsira:{PASSWORD}@127.0.0.1:5432/tabsira"
PRODUCTION = {
    "environment": "production",
    "database_url": DATABASE_URL,
    "site_url": "https://tabsira.me",
    "api_url": "https://api.tabsira.me",
    "cors_origins": "https://tabsira.me",
    "ai_ovh": {"api_key": "ovh-key-123"},
}


def errors_of(**values: object) -> str:
    """Return the message `load_settings` produces when the values are rejected."""
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, **values)
    return format_validation_error(caught.value)


def test_development_defaults(make_settings):
    settings = make_settings(environment="development", database_url=DATABASE_URL)

    assert settings.environment is Environment.DEVELOPMENT
    assert (settings.api_host, settings.api_port) == ("127.0.0.1", 8000)
    assert settings.site_url == "https://tabsira.test"
    assert settings.api_url == "https://api.tabsira.test"
    assert settings.cors_origins == ["https://tabsira.test"]
    assert settings.db_connect_timeout == 3.0
    assert settings.sync_database_url is None
    assert settings.test_database_url is None
    assert not settings.is_production


def test_feature_flags_default_and_can_be_switched(make_settings, monkeypatch):
    settings = make_settings()
    flags = {name: getattr(settings, name) for name in Settings.model_fields if "feature_" in name}

    assert set(flags) == {
        "feature_chat",
        "feature_world",
        "feature_treasure",
        "feature_social",
        "feature_atlas",
        "feature_camera_discovery",
        "feature_camera_anchor",
        "feature_photo_storage",
        "feature_canonical_verify",
        "feature_admin",
    }
    # Anchoring stays off until it is proven on devices; everything else is on.
    assert [name for name, on in flags.items() if not on] == ["feature_camera_anchor"]

    monkeypatch.setenv("FEATURE_CHAT", "false")
    monkeypatch.setenv("FEATURE_CAMERA_ANCHOR", "true")
    switched = make_settings()
    assert switched.feature_chat is False
    assert switched.feature_camera_anchor is True


def test_ai_defaults_name_both_providers_and_no_models(make_settings):
    settings = make_settings()

    assert settings.ai_provider is AiProvider.OVH
    assert settings.ai_ovh.base_url == config.OVH_BASE_URL
    assert settings.ai_openai.base_url == config.OPENAI_BASE_URL
    for stage in AiStage:
        assert settings.ai_ovh.model_for(stage) == ""
        assert settings.ai_openai.model_for(stage) == ""


def test_ai_property_follows_the_provider_switch(make_settings, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")

    settings = make_settings()

    assert settings.ai is settings.ai_openai
    assert make_settings(ai_provider="ovh").ai is not settings.ai_openai


def test_provider_blocks_are_read_from_nested_keys(make_settings, monkeypatch):
    monkeypatch.setenv("AI_OVH__API_KEY", "ovh-secret")
    monkeypatch.setenv("AI_OVH__VISION_MODEL", "qwen-vl")
    monkeypatch.setenv("AI_OPENAI__GUARD_MODEL", "guard-1")
    monkeypatch.setenv("AI_OPENAI__BASE_URL", "https://proxy.example/v1")

    settings = make_settings()

    assert settings.ai_ovh.api_key.get_secret_value() == "ovh-secret"
    assert settings.ai_ovh.model_for(AiStage.VISION) == "qwen-vl"
    # An unset key in a block keeps the provider's own default.
    assert settings.ai_ovh.base_url == config.OVH_BASE_URL
    assert settings.ai_openai.model_for(AiStage.GUARD) == "guard-1"
    assert settings.ai_openai.base_url == "https://proxy.example/v1"


def test_a_misspelt_provider_key_stops_startup_instead_of_being_ignored(monkeypatch):
    monkeypatch.setenv("AI_OVH__VISON_MODEL", "qwen-vl")

    with pytest.raises(ConfigError) as caught:
        load_settings()

    assert "AI_OVH__VISON_MODEL: Extra inputs are not permitted" in str(caught.value)


def test_every_stage_has_a_model_field(make_settings):
    settings = make_settings(ai_ovh={f"{stage.value}_model": stage.value for stage in AiStage})

    assert [settings.ai_ovh.model_for(stage) for stage in AiStage] == [s.value for s in AiStage]


def test_secrets_never_appear_in_repr_or_str(make_settings):
    settings = make_settings(
        database_url=DATABASE_URL,
        sync_database_url=SYNC_URL,
        test_database_url=DATABASE_URL + "_test",
        ai_ovh={"api_key": "ovh-secret-key"},
        ai_openai={"api_key": "openai-secret-key"},
    )

    shown = repr(settings) + str(settings) + repr(settings.ai) + settings.model_dump_json()

    for secret in (PASSWORD, "ovh-secret-key", "openai-secret-key"):
        assert secret not in shown


def test_settings_are_read_from_a_dotenv_file(tmp_path: Path, monkeypatch):
    for key in ("ENVIRONMENT", "FEATURE_CHAT"):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_CHAT=false\nAPI_PORT=8123\nSOME_OTHER_APP_KEY=ignored\n")

    settings = Settings(_env_file=env_file)

    assert settings.feature_chat is False
    assert settings.api_port == 8123


# ─── Required and invalid keys ─────────────────────────────────────


def test_a_missing_database_url_stops_startup_with_the_key_name(monkeypatch):
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ConfigError) as caught:
        load_settings()

    assert "DATABASE_URL: Field required" in str(caught.value)
    assert "Invalid configuration" in str(caught.value)


def test_every_bad_key_is_listed_at_once(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prodcution")
    monkeypatch.setenv("API_PORT", "not-a-port")

    with pytest.raises(ConfigError) as caught:
        load_settings()

    message = str(caught.value)
    assert "ENVIRONMENT" in message
    assert "API_PORT" in message


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("postgresql://tabsira:pw@127.0.0.1/tabsira", "must use the postgresql+asyncpg driver"),
        ("postgresql+psycopg://tabsira:pw@127.0.0.1/tabsira", "must use the postgresql+asyncpg"),
        ("postgresql+asyncpg://tabsira:pw@localhost/tabsira", "127.0.0.1, not localhost"),
        ("postgresql+asyncpg://tabsira:pw@127.0.0.1", "must include a host and a database name"),
        ("postgresql+asyncpg://tabsira:pw@/tabsira", "must include a host and a database name"),
        ("not a url at all pw", "must be a URL of the form"),
        ("", "must be a URL of the form"),
    ],
)
def test_database_url_is_validated_and_never_echoed(url, reason):
    message = errors_of(database_url=url)

    assert "DATABASE_URL" in message
    assert reason in message
    assert "pw" not in message.replace("postgresql", "").replace("password", "")


def test_a_raw_validation_error_never_echoes_the_rejected_value():
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, database_url=f"postgresql://tabsira:{PASSWORD}@localhost/tabsira")

    assert PASSWORD not in str(caught.value)


def test_sync_database_url_is_validated(make_settings):
    assert "must use the postgresql+psycopg driver" in errors_of(
        sync_database_url="postgresql+asyncpg://tabsira:pw@127.0.0.1/tabsira"
    )
    assert make_settings(sync_database_url=SYNC_URL).sync_database_url is not None
    assert make_settings(sync_database_url="").sync_database_url is None


def test_test_database_must_end_in_test(make_settings):
    assert "ending in _test" in errors_of(test_database_url=DATABASE_URL)
    assert "TEST_DATABASE_URL" in errors_of(
        test_database_url="postgresql://tabsira:pw@127.0.0.1/tabsira_test"
    )
    assert make_settings(test_database_url=DATABASE_URL + "_test").test_database_url is not None
    assert make_settings(test_database_url="").test_database_url is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://tabsira.test", "https://tabsira.test"),
        ("https://tabsira.me/", "https://tabsira.me"),
        ("http://127.0.0.1:3000", "http://127.0.0.1:3000"),
        (" https://tabsira.me ", "https://tabsira.me"),
    ],
)
def test_public_urls_are_normalised(make_settings, value, expected):
    settings = make_settings(site_url=value, api_url=value)

    assert (settings.site_url, settings.api_url) == (expected, expected)


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("ftp://tabsira.me", "http(s) URL with a host"),
        ("tabsira.me", "http(s) URL with a host"),
        ("https://", "http(s) URL with a host"),
        ("https://tabsira.me/path", "no path"),
        ("https://tabsira.me?x=1", "no path"),
        ("https://tabsira.me#top", "no path"),
    ],
)
def test_public_urls_are_rejected_when_malformed(value, reason):
    message = errors_of(site_url=value)

    assert "SITE_URL" in message
    assert reason in message


def test_cors_origins_accept_a_comma_separated_string_or_a_list(make_settings, monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://tabsira.me/, https://www.tabsira.me ,,")

    assert make_settings().cors_origins == ["https://tabsira.me", "https://www.tabsira.me"]
    assert make_settings(cors_origins=["https://a.example"]).cors_origins == ["https://a.example"]


def test_cors_origins_refuse_a_wildcard_and_a_path(make_settings):
    assert "CORS_ORIGINS" in errors_of(cors_origins="*")
    assert "no path" in errors_of(cors_origins="https://tabsira.me/app")


# ─── Production ────────────────────────────────────────────────────


def test_a_correct_production_configuration_is_accepted(make_settings):
    settings = make_settings(**PRODUCTION)

    assert settings.is_production
    assert settings.ai.api_key.get_secret_value() == "ovh-key-123"


def test_production_refuses_every_test_domain_url():
    message = errors_of(
        **{**PRODUCTION, "site_url": "https://tabsira.test", "api_url": "https://api.tabsira.test"}
    )

    assert "SITE_URL points at the development host https://tabsira.test" in message
    assert "API_URL points at the development host https://api.tabsira.test" in message


def test_production_refuses_a_test_domain_cors_origin():
    message = errors_of(
        **{**PRODUCTION, "cors_origins": "https://tabsira.me,https://x.tabsira.test"}
    )

    assert "CORS_ORIGINS points at the development host https://x.tabsira.test" in message
    assert "https://tabsira.me " not in message


def test_production_refuses_the_bare_test_host():
    assert "development host" in errors_of(**{**PRODUCTION, "site_url": "https://test"})


def test_production_refuses_the_development_defaults_left_in_place():
    values = {"environment": "production", "database_url": DATABASE_URL}

    message = errors_of(**values)

    assert "SITE_URL" in message
    assert "API_URL" in message
    assert "CORS_ORIGINS" in message
    assert "the key of the active AI provider (ovh) is empty" in message


def test_production_requires_the_key_of_the_active_provider(make_settings):
    values = {**PRODUCTION, "ai_ovh": {"api_key": ""}}
    assert "key of the active AI provider (ovh) is empty" in errors_of(**values)

    # The other provider's key does not count.
    values = {**values, "ai_openai": {"api_key": "openai-key"}}
    assert "key of the active AI provider (ovh) is empty" in errors_of(**values)

    values = {**values, "ai_provider": "openai"}
    assert make_settings(**values).ai.api_key.get_secret_value() == "openai-key"


def test_development_accepts_test_domains_and_no_ai_key(make_settings):
    settings = make_settings(environment="development")

    assert settings.site_url.endswith(".test")
    assert settings.ai.api_key.get_secret_value() == ""


# ─── Loading ───────────────────────────────────────────────────────


def test_format_names_model_level_errors_as_settings():
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, **{**PRODUCTION, "site_url": "https://tabsira.test"})

    message = format_validation_error(caught.value)

    assert message.startswith("Invalid configuration, fix the .env:\n  - SETTINGS: Refusing")


def test_get_settings_reads_once_and_raises_config_error(monkeypatch):
    get_settings.cache_clear()
    try:
        first = get_settings()
        assert get_settings() is first

        get_settings.cache_clear()
        monkeypatch.delenv("DATABASE_URL")
        with pytest.raises(ConfigError):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_env_files_walk_up_from_a_checkout_and_end_with_the_working_directory(monkeypatch):
    monkeypatch.delenv(config.ENV_FILE_OVERRIDE)
    here = Path("/work/tabsira/apps/api/src/config.py")

    files = config._env_files(here)

    # Farthest first, so the nearest file wins; the repository root is among them.
    assert files == (
        Path("/work/tabsira/.env"),
        Path("/work/tabsira/apps/.env"),
        Path("/work/tabsira/apps/api/.env"),
        Path("/work/tabsira/apps/api/src/.env"),
        Path(".env"),
    )


def test_env_files_cope_with_a_shallow_container_layout(monkeypatch):
    monkeypatch.delenv(config.ENV_FILE_OVERRIDE)

    files = config._env_files(Path("/app/src/config.py"))

    assert files == (Path("/.env"), Path("/app/.env"), Path("/app/src/.env"), Path(".env"))


def test_the_env_file_override_replaces_or_disables_the_lookup(monkeypatch):
    monkeypatch.setenv(config.ENV_FILE_OVERRIDE, "/srv/elsewhere.env")
    assert config._env_files(Path("/app/src/config.py")) == (Path("/srv/elsewhere.env"),)

    monkeypatch.setenv(config.ENV_FILE_OVERRIDE, "")
    assert config._env_files(Path("/app/src/config.py")) == ()
