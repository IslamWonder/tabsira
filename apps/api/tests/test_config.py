from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src import config
from src.config import (
    DEV_REDIS_URL,
    AiProvider,
    AiStage,
    BoxCoordinates,
    ConfigError,
    Environment,
    GeonamesSource,
    ProviderSettings,
    RerankerKind,
    ScanEngine,
    Settings,
    format_validation_error,
    get_settings,
    load_settings,
)

PASSWORD = "s3cr3t-pw"
# A Fernet key: 32 bytes as url-safe base64. Only ever used by these tests.
FERNET_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
OTHER_FERNET_KEY = "ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8="
DATABASE_URL = f"postgresql+asyncpg://tabsira:{PASSWORD}@127.0.0.1:5432/tabsira"
SYNC_URL = f"postgresql+psycopg://tabsira:{PASSWORD}@127.0.0.1:5432/tabsira"
PRODUCTION = {
    "environment": "production",
    "database_url": DATABASE_URL,
    "site_url": "https://tabsira.me",
    "api_url": "https://api.tabsira.me",
    "admin_url": "https://admin.tabsira.me",
    "cors_origins": "https://tabsira.me",
    "session_cookie_domain": ".tabsira.me",
    "hash_secret": "not-a-real-secret-but-long-enough-for-the-rule",
    "ai_provider": "ovh",
    "admin_totp_encryption_key": FERNET_KEY,
    "ai_ovh": {"api_key": "ovh-key-123"},
    "redis_password": "redis-secret",
    "s3_bucket": "tabsira-photos",
    "s3_access_key_id": "AKIAEXAMPLE",
    "s3_secret_access_key": "s3-secret-value",
    "s3_public_base_url": "https://media.tabsira.me",
}


def errors_of(**values: object) -> str:
    """Return the message `load_settings` produces when the values are rejected."""
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, **values)
    return format_validation_error(caught.value)


def test_development_defaults(make_settings, monkeypatch):
    # The suite pins https addresses; the code's own defaults are plain http (decision 49).
    for key in ("SITE_URL", "API_URL", "ADMIN_URL", "CORS_ORIGINS", "GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(key)
    settings = make_settings(environment="development", database_url=DATABASE_URL)

    assert settings.environment is Environment.DEVELOPMENT
    assert (settings.api_host, settings.api_port) == ("127.0.0.1", 8000)
    assert settings.site_url == "http://tabsira.test"
    assert settings.api_url == "http://api.tabsira.test"
    assert settings.admin_url == "http://admin.tabsira.test"
    assert settings.admin_host == "admin.tabsira.test"
    assert settings.cors_origins == ["http://tabsira.test"]
    assert settings.google_redirect_uri == "http://api.tabsira.test/auth/google/callback"
    assert settings.cookie_secure is False
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
        "feature_dev_inspector",
    }
    # Anchoring stays off until it is proven on devices; everything else is on.
    assert [name for name, on in flags.items() if not on] == ["feature_camera_anchor"]

    monkeypatch.setenv("FEATURE_CHAT", "false")
    monkeypatch.setenv("FEATURE_CAMERA_ANCHOR", "true")
    switched = make_settings()
    assert switched.feature_chat is False
    assert switched.feature_camera_anchor is True


def test_ai_defaults_are_what_the_benchmark_measured(make_settings):
    settings = make_settings()

    # docs/BENCHMARK.md, 4 October 2026: the vision stage, the guard and the embeddings.
    assert settings.ai_provider is AiProvider.OPENAI
    assert settings.ai_ovh.base_url == config.OVH_BASE_URL
    assert settings.ai_openai.base_url == config.OPENAI_BASE_URL
    assert settings.ai_ovh.model_for(AiStage.VISION) == "Qwen3.8-27B"
    assert settings.ai_ovh.reasoning_effort == "none"
    assert settings.ai_ovh.box_coordinates is BoxCoordinates.THOUSANDTHS
    assert settings.ai_openai.model_for(AiStage.VISION) == "gpt-5.4-mini-2026-03-17"
    assert settings.ai_openai.model_for(AiStage.GUARD) == "omni-moderation-latest"
    assert settings.ai_openai.reasoning_effort == "none"
    assert settings.ai_openai.box_coordinates is BoxCoordinates.PIXELS
    # Decision 46: the chat answers with the insight stages' model of the provider.
    assert settings.ai_openai.model_for(AiStage.CHAT) == "gpt-5.4-mini-2026-03-17"
    assert settings.ai_ovh.model_for(AiStage.CHAT) == "Qwen3.8-27B"
    # The retrieval benchmark measured the embeddings; the insight stages follow the vision
    # model and are measured end to end by docs/EVALUATION.md.
    assert settings.ai_openai.model_for(AiStage.EMBEDDING) == "text-embedding-3-large"
    assert settings.ai_openai.embedding_dimensions == 1536
    assert settings.ai_ovh.model_for(AiStage.EMBEDDING) == "bge-m3"
    assert settings.ai_ovh.embedding_dimensions is None
    # Decision 50: no reranking by default; the small text model stays set for RERANKER=llm.
    assert settings.reranker is RerankerKind.OFF
    assert settings.ai_openai.model_for(AiStage.RERANK) == "gpt-5.4-nano-2026-03-17"
    assert settings.ai_ovh.model_for(AiStage.RERANK) == ""
    text_stages = (AiStage.PLANNER, AiStage.VERIFY, AiStage.COMPOSE)
    for block in (settings.ai_ovh, settings.ai_openai):
        assert {block.model_for(stage) for stage in text_stages} == {block.vision_model}
    set_by_a_measure = {AiStage.VISION, AiStage.EMBEDDING, AiStage.CHAT, *text_stages}
    for provider, block in (
        (AiProvider.OVH, settings.ai_ovh),
        (AiProvider.OPENAI, settings.ai_openai),
    ):
        for stage in AiStage:
            if stage not in set_by_a_measure and (provider, stage) not in {
                (AiProvider.OPENAI, AiStage.GUARD),
                (AiProvider.OPENAI, AiStage.RERANK),
            }:
                assert block.model_for(stage) == "", (provider, stage)


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


def test_ai_call_limits_default_and_are_bounded(make_settings):
    settings = make_settings()

    assert settings.ai_timeout_seconds == 90.0
    assert settings.ai_max_retries == 2
    assert settings.ai_retry_backoff_seconds == 1.0
    assert "AI_MAX_RETRIES" in errors_of(ai_max_retries=6)
    assert "AI_TIMEOUT_SECONDS" in errors_of(ai_timeout_seconds=0)
    assert "AI_RETRY_BACKOFF_SECONDS" in errors_of(ai_retry_backoff_seconds=-1)


def test_the_profile_questions_count_defaults_to_three_and_stays_between_zero_and_three(
    make_settings,
):
    assert make_settings().profile_questions_max == 3
    assert make_settings(profile_questions_max=0).profile_questions_max == 0
    assert "PROFILE_QUESTIONS_MAX" in errors_of(profile_questions_max=4)
    assert "PROFILE_QUESTIONS_MAX" in errors_of(profile_questions_max=-1)


def test_each_provider_carries_its_price_table(make_settings, monkeypatch):
    settings = make_settings()

    assert settings.ai_ovh.prices["Qwen3.8-27B"].output == 3.19
    assert settings.ai_openai.prices["gpt-5.4-mini-2026-03-17"].cached_input == 0.075
    assert "gpt-5.4-mini-2026-03-17" not in settings.ai_ovh.prices

    monkeypatch.setenv("AI_OVH__PRICES", '{"Qwen3.5-9B": {"input": 0.2, "output": 0.3}}')
    replaced = make_settings()
    assert list(replaced.ai_ovh.prices) == ["Qwen3.5-9B"]
    assert replaced.ai_ovh.prices["Qwen3.5-9B"].cached_input is None


def test_a_negative_or_unknown_price_field_is_refused():
    assert "AI_OVH__PRICES" in errors_of(ai_ovh={"prices": {"m": {"input": -1}}})
    assert "Extra inputs" in errors_of(ai_ovh={"prices": {"m": {"input": 1, "outptu": 2}}})


@pytest.mark.parametrize(
    "values",
    [
        {"ai_ovh": {"vision_model": "gpt-oss-120b"}},
        {"ai_openai": {"chat_model": "GPT-OSS-20B"}},
        {"ai_openai": {"guard_model": "openai/gpt_oss_safeguard"}},
        {"ai_ovh": {"prices": {"gpt-oss-20b": {"input": 0.05}}}},
    ],
)
def test_gpt_oss_models_are_refused_everywhere(values):
    message = errors_of(**values)

    assert "is a gpt-oss model, which this project never uses" in message


def test_box_coordinates_can_be_switched_per_provider(make_settings, monkeypatch):
    assert ProviderSettings().box_coordinates is BoxCoordinates.PIXELS

    monkeypatch.setenv("AI_OVH__BOX_COORDINATES", "pixels")

    assert make_settings().ai_ovh.box_coordinates is BoxCoordinates.PIXELS
    assert "AI_OVH__BOX_COORDINATES" in errors_of(ai_ovh={"box_coordinates": "inches"})


def test_reasoning_effort_accepts_only_the_known_levels(make_settings):
    assert (
        make_settings(ai_openai={"reasoning_effort": "none"}).ai_openai.reasoning_effort == "none"
    )
    assert make_settings().ai_ovh.reasoning_effort == "none"
    assert ProviderSettings().reasoning_effort == ""
    assert "AI_OVH__REASONING_EFFORT" in errors_of(ai_ovh={"reasoning_effort": "maximum"})


def test_the_detector_is_a_loopback_origin_by_default(make_settings):
    settings = make_settings()

    assert settings.detector_url == "http://127.0.0.1:8100"
    assert settings.detector_timeout_seconds == 30.0
    assert make_settings(detector_url="http://10.0.0.5:8100/").detector_url == (
        "http://10.0.0.5:8100"
    )
    assert "no path" in errors_of(detector_url="http://127.0.0.1:8100/detect")
    assert "DETECTOR_TIMEOUT_SECONDS" in errors_of(detector_timeout_seconds=0)


def test_image_limits_default_to_15_megabytes_and_40_megapixels(make_settings):
    settings = make_settings()

    assert settings.image_max_bytes == 15 * 1024 * 1024
    assert settings.image_max_pixels == 40_000_000
    assert "IMAGE_MAX_BYTES" in errors_of(image_max_bytes=0)
    assert "IMAGE_MAX_PIXELS" in errors_of(image_max_pixels=-1)


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
    settings = make_settings(site_url=value, api_url=value, admin_url=value)

    assert (settings.site_url, settings.api_url, settings.admin_url) == (expected,) * 3


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


@pytest.mark.parametrize("prefix", ["1x", "2x", "3x"])
def test_production_refuses_cloudflares_dummy_turnstile_keys(prefix):
    message = errors_of(
        **PRODUCTION,
        turnstile_site_key=f"{prefix}00000000000000000000AA",
        turnstile_secret_key=f"{prefix}0000000000000000000000000000AA",
    )

    assert "TURNSTILE_SITE_KEY is one of Cloudflare's test keys" in message
    assert "TURNSTILE_SECRET_KEY is one of Cloudflare's test keys" in message


@pytest.mark.parametrize("site_key", ["0x4AAA", "0x4AAAAAAAexample key", "0x4AAAAAAA" + "a" * 60])
def test_production_refuses_a_site_key_the_web_app_would_drop(site_key):
    message = errors_of(
        **PRODUCTION, turnstile_site_key=site_key, turnstile_secret_key="0x4AAAAAAAsecretvalue"
    )

    assert "TURNSTILE_SITE_KEY must be 8 to 64 letters, digits, - or _" in message


@pytest.mark.parametrize(
    ("given", "missing"),
    [
        ({"turnstile_site_key": "0x4AAAAAAAexample-key_1"}, "TURNSTILE_SECRET_KEY"),
        ({"turnstile_secret_key": "0x4AAAAAAAsecretvalue"}, "TURNSTILE_SITE_KEY"),
    ],
)
def test_one_turnstile_key_without_the_other_is_refused(given, missing):
    message = errors_of(**given)

    assert f"{missing} must be set together with the other Turnstile key" in message


def test_production_accepts_real_looking_turnstile_keys(make_settings):
    settings = make_settings(
        **PRODUCTION,
        turnstile_site_key="0x4AAAAAAAexample-key_1",
        turnstile_secret_key="0x4AAAAAAAsecretvalue",
    )

    assert settings.turnstile_enabled


def test_production_leaves_turnstile_alone_when_it_is_off(make_settings):
    assert not make_settings(**PRODUCTION).turnstile_enabled


def test_production_refuses_every_test_domain_url():
    message = errors_of(
        **{
            **PRODUCTION,
            "site_url": "https://tabsira.test",
            "api_url": "https://api.tabsira.test",
            "admin_url": "https://admin.tabsira.test",
        }
    )

    assert "SITE_URL points at the development host https://tabsira.test" in message
    assert "API_URL points at the development host https://api.tabsira.test" in message
    assert "ADMIN_URL points at the development host https://admin.tabsira.test" in message


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
    assert "the key of the active AI provider (openai) is empty" in message


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


# ─── Accounts, sessions, Google and mail ───────────────────────────


def test_account_defaults(make_settings):
    settings = make_settings()

    assert settings.session_cookie_name == "__Secure-tabsira_session"
    assert settings.session_cookie_domain == ".tabsira.test"
    assert settings.session_ttl_days == 30
    assert settings.hash_secret.get_secret_value() == ""
    assert settings.password_bcrypt_rounds == 12
    assert (
        settings.auth_attempt_window_seconds,
        settings.auth_max_attempts_per_ip,
        settings.auth_max_attempts_per_email,
    ) == (900, 20, 5)
    assert settings.google_client_id == ""
    assert not settings.google_configured
    assert settings.google_redirect_uri == "https://api.tabsira.test/auth/google/callback"
    assert settings.google_state_ttl_seconds == 600
    assert (settings.smtp_host, settings.smtp_port, settings.smtp_security) == ("", 587, "starttls")
    assert settings.mail_from == "تبصرة <no-reply@tabsira.me>"
    assert not settings.smtp_configured


def test_derived_values(make_settings):
    settings = make_settings(
        session_ttl_days=2,
        google_client_id=" the-id ",
        smtp_host="smtp.example.com",
        site_url="https://tabsira.example",
        api_url="https://api.tabsira.example",
        cors_origins="https://tabsira.example,https://www.tabsira.example",
    )

    assert settings.session_ttl.total_seconds() == 2 * 86400
    assert settings.google_client_id == "the-id"
    assert settings.google_configured
    assert settings.smtp_configured
    assert settings.mail_link_base == "https://tabsira.example"
    assert settings.allowed_origins == {
        "https://tabsira.example",
        "https://www.tabsira.example",
        "https://api.tabsira.example",
    }
    assert (
        make_settings(web_base_url="https://web.example/").mail_link_base == "https://web.example"
    )
    assert not make_settings(smtp_host="smtp.example.com", mail_from="").smtp_configured


def test_the_hash_key_is_the_secret_or_one_derived_from_the_database_url(make_settings):
    explicit = make_settings(hash_secret="s" * 40)
    one = make_settings(database_url="postgresql+asyncpg://u:one@127.0.0.1/db")
    two = make_settings(database_url="postgresql+asyncpg://u:two@127.0.0.1/db")

    assert explicit.hash_key == b"s" * 40
    assert len(one.hash_key) == 32
    assert (
        one.hash_key
        == make_settings(database_url="postgresql+asyncpg://u:one@127.0.0.1/db").hash_key
    )
    assert one.hash_key != two.hash_key
    assert b"one" not in one.hash_key


@pytest.mark.parametrize("name", ["__Host-session", "has space", "semi;colon", "", "x" * 65])
def test_a_session_cookie_name_must_be_a_plain_token(name):
    assert "SESSION_COOKIE_NAME" in errors_of(session_cookie_name=name)


@pytest.mark.parametrize("domain", ["tabsira", "https://tabsira.me", ".tabsira..me", "ta bsira.me"])
def test_a_cookie_domain_must_be_a_domain(domain):
    assert "SESSION_COOKIE_DOMAIN" in errors_of(session_cookie_domain=domain)


def test_a_cookie_domain_is_lower_cased_and_may_be_empty_for_a_host_only_cookie(make_settings):
    assert (
        make_settings(session_cookie_domain=" .Tabsira.ME ").session_cookie_domain == ".tabsira.me"
    )
    assert make_settings(session_cookie_domain="").session_cookie_domain == ""


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("session_ttl_days", 0),
        ("session_ttl_days", 366),
        ("password_bcrypt_rounds", 3),
        ("password_bcrypt_rounds", 17),
        ("auth_attempt_window_seconds", 0),
        ("auth_max_attempts_per_ip", 0),
        ("auth_max_attempts_per_email", 0),
        ("google_state_ttl_seconds", 10),
        ("smtp_port", 0),
        ("smtp_port", 70000),
        ("smtp_timeout_seconds", 0),
        ("email_verification_expire_hours", 0),
        ("password_reset_expire_minutes", 1),
    ],
)
def test_numbers_have_bounds(key, value):
    assert key.upper() in errors_of(**{key: value})


@pytest.mark.parametrize(
    "uri", ["/auth/google/callback", "ftp://x.example/cb", "https://x.example/cb#frag"]
)
def test_the_google_redirect_uri_must_be_a_full_url(uri):
    assert "GOOGLE_REDIRECT_URI" in errors_of(google_redirect_uri=uri)


def test_mail_addresses_are_checked_but_a_name_is_allowed(make_settings):
    assert "MAIL_FROM" in errors_of(mail_from="not an address")
    assert "MAIL_REPLY_TO" in errors_of(mail_reply_to="nobody")
    assert make_settings(mail_reply_to="").mail_reply_to == ""
    assert make_settings(mail_reply_to=" help@tabsira.me ").mail_reply_to == "help@tabsira.me"


def test_the_web_base_url_is_an_origin_or_empty(make_settings):
    assert "WEB_BASE_URL" in errors_of(web_base_url="https://tabsira.me/app")
    assert make_settings(web_base_url="  ").web_base_url == ""


def test_the_smtp_ca_file_must_exist(make_settings, tmp_path):
    assert "SMTP_CA_FILE" in errors_of(smtp_ca_file=str(tmp_path / "missing.pem"))
    ca = tmp_path / "ca.pem"
    ca.write_text("-")

    assert make_settings(smtp_ca_file=str(ca)).smtp_ca_file == str(ca)
    assert make_settings(smtp_ca_file="").smtp_ca_file == ""


def test_smtp_security_is_starttls_or_ssl_only():
    assert "SMTP_SECURITY" in errors_of(smtp_security="none")


def test_production_refuses_a_development_cookie_domain_a_short_secret_and_cheap_bcrypt():
    values = {
        **PRODUCTION,
        "session_cookie_domain": ".tabsira.test",
        "hash_secret": "short",
        "password_bcrypt_rounds": 10,
    }

    message = errors_of(**values)

    assert "SESSION_COOKIE_DOMAIN is the development domain .tabsira.test" in message
    assert "HASH_SECRET must hold at least 32 characters" in message
    assert "PASSWORD_BCRYPT_ROUNDS is under 12" in message


def test_production_with_google_needs_its_secret_and_a_real_redirect():
    values = {**PRODUCTION, "google_client_id": "id"}

    message = errors_of(**values)

    assert "GOOGLE_CLIENT_ID is set but GOOGLE_CLIENT_SECRET is empty" in message
    assert "GOOGLE_REDIRECT_URI points at the development host" in message


def test_production_accepts_google_when_it_is_complete(make_settings):
    settings = make_settings(
        **PRODUCTION,
        google_client_id="id",
        google_client_secret="secret",
        google_redirect_uri="https://api.tabsira.me/auth/google/callback",
    )

    assert settings.google_configured


def test_production_leaves_google_alone_when_it_is_off(make_settings):
    assert not make_settings(**PRODUCTION).google_configured


def test_production_refuses_a_development_web_base_url():
    message = errors_of(**{**PRODUCTION, "web_base_url": "https://tabsira.test"})

    assert "WEB_BASE_URL points at the development host https://tabsira.test" in message


# ─── Error tracking ────────────────────────────────────────────────

DSN = "https://public-key@glitchtip.example.com/7"


def test_error_tracking_is_off_by_default(make_settings):
    settings = make_settings()

    assert settings.glitchtip_configured is False
    assert settings.glitchtip_web_dsn_value == ""
    assert settings.glitchtip_traces_sample_rate == 0.0
    assert settings.glitchtip_release == ""


def test_a_dsn_turns_reporting_on_and_the_web_project_falls_back_to_it(make_settings):
    api_only = make_settings(glitchtip_dsn=f" {DSN} ")
    assert api_only.glitchtip_configured
    assert api_only.glitchtip_dsn.get_secret_value() == DSN
    assert api_only.glitchtip_web_dsn_value == DSN

    both = make_settings(glitchtip_dsn=DSN, glitchtip_web_dsn="https://k@glitchtip.example.com/8")
    assert both.glitchtip_web_dsn_value == "https://k@glitchtip.example.com/8"

    web_only = make_settings(glitchtip_web_dsn=DSN)
    assert web_only.glitchtip_configured is False
    assert web_only.glitchtip_web_dsn_value == DSN


@pytest.mark.parametrize("key", ["glitchtip_dsn", "glitchtip_web_dsn"])
def test_a_malformed_dsn_is_refused_without_being_echoed(key):
    message = errors_of(**{key: "https://secret-key-not-a-dsn"})

    assert key.upper() in message
    assert "must be empty or a DSN" in message
    assert "secret-key-not-a-dsn" not in message


def test_the_dsn_is_a_secret(make_settings):
    settings = make_settings(glitchtip_dsn=DSN)

    assert "public-key" not in repr(settings) + settings.model_dump_json()


@pytest.mark.parametrize("rate", [-0.1, 1.5])
def test_the_trace_rate_is_a_share_between_zero_and_one(rate):
    assert "GLITCHTIP_TRACES_SAMPLE_RATE" in errors_of(glitchtip_traces_sample_rate=rate)


def test_the_release_override_is_a_plain_version():
    assert "GLITCHTIP_RELEASE" in errors_of(glitchtip_release="1.0 beta")


def test_production_refuses_a_development_error_tracker_host():
    message = errors_of(
        **{
            **PRODUCTION,
            "glitchtip_dsn": "https://k@errors.tabsira.test/1",
            "glitchtip_web_dsn": "https://k@errors.tabsira.test/2",
        }
    )

    assert "GLITCHTIP_DSN points at a development host" in message
    assert "GLITCHTIP_WEB_DSN points at a development host" in message


def test_production_accepts_a_real_error_tracker_host(make_settings):
    assert make_settings(**PRODUCTION, glitchtip_dsn=DSN).glitchtip_configured


# ─── Cookie consent ────────────────────────────────────────────────


def test_cookie_consent_defaults_to_a_version_and_six_months(make_settings):
    settings = make_settings()

    assert settings.cookie_policy_version == "2026-10-04"
    assert settings.consent_reask_days == 182
    assert settings.consent_reask.days == 182


@pytest.mark.parametrize("version", ["has space", "", "x" * 33, "bad/slash"])
def test_the_cookie_policy_version_is_a_short_plain_token(version):
    assert "COOKIE_POLICY_VERSION" in errors_of(cookie_policy_version=version)


@pytest.mark.parametrize("days", [0, -1, 731])
def test_the_reask_interval_is_between_a_day_and_two_years(days):
    assert "CONSENT_REASK_DAYS" in errors_of(consent_reask_days=days)


# ─── Photo storage ─────────────────────────────────────────────────

S3 = {
    "storage_backend": "s3",
    "s3_bucket": "tabsira-photos",
    "s3_access_key_id": "AKIAEXAMPLE",
    "s3_secret_access_key": "s3-secret-value",
    "s3_public_base_url": "https://media.tabsira.me/",
}


def test_photos_are_kept_on_local_disk_by_default_with_a_short_link_life(make_settings):
    settings = make_settings()

    assert settings.storage_backend == "auto"
    assert settings.resolved_storage_backend == "local"
    assert settings.signed_url_ttl_seconds == 300
    assert (settings.s3_endpoint_url, settings.s3_bucket, settings.s3_public_base_url) == (
        "",
        "",
        "",
    )
    assert settings.s3_region == "us-east-1"
    assert settings.s3_secret_access_key.get_secret_value() == ""


def test_the_s3_backend_needs_every_key_and_names_the_ones_that_are_missing():
    message = errors_of(storage_backend="s3")

    assert "STORAGE_BACKEND=s3 needs S3_BUCKET, S3_ACCESS_KEY_ID, S3_PUBLIC_BASE_URL" in message
    assert message.endswith("S3_SECRET_ACCESS_KEY")
    only_secret = errors_of(**{**S3, "s3_secret_access_key": ""})
    assert "needs S3_SECRET_ACCESS_KEY" in only_secret
    assert "S3_BUCKET" not in only_secret


def test_the_s3_keys_are_not_needed_while_photos_stay_on_disk(make_settings):
    assert make_settings(storage_backend="local").storage_backend == "local"


def test_auto_picks_s3_when_a_bucket_is_set_and_the_disk_otherwise(make_settings):
    assert make_settings().resolved_storage_backend == "local"
    assert make_settings(**{**S3, "storage_backend": "auto"}).resolved_storage_backend == "s3"
    assert make_settings(**{**S3, "storage_backend": "local"}).resolved_storage_backend == "local"
    assert make_settings(**S3).resolved_storage_backend == "s3"


def test_auto_with_a_half_filled_bucket_refuses_instead_of_falling_back_to_disk():
    message = errors_of(s3_bucket="tabsira-photos")

    assert "S3_BUCKET is set, so photos go to S3, which needs S3_ACCESS_KEY_ID" in message


def test_the_local_folder_defaults_to_the_checkout_and_follows_the_setting(
    make_settings, tmp_path, monkeypatch
):
    # The suite sends kept photos to a folder of its run; the default is what is tested here.
    monkeypatch.delenv("LOCAL_MEDIA_DIR", raising=False)

    assert make_settings().local_media_path == config.checkout_root() / "data" / "media"
    assert make_settings(local_media_dir=f" {tmp_path} ").local_media_path == tmp_path.resolve()


def test_outside_a_checkout_the_root_is_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHECKOUT_MARKER", "no-such-marker-file")
    monkeypatch.chdir(tmp_path)

    assert config.checkout_root() == tmp_path


def test_production_refuses_the_local_disk_even_when_asked_for_it():
    message = errors_of(**{**PRODUCTION, "storage_backend": "local"})

    assert "photos must be kept in S3 in production" in message


def test_production_without_any_s3_setting_is_refused():
    without_s3 = {k: v for k, v in PRODUCTION.items() if not k.startswith("s3_")}

    assert "photos must be kept in S3 in production" in errors_of(**without_s3)


def test_production_with_a_bucket_but_missing_keys_is_refused():
    message = errors_of(**{**PRODUCTION, "s3_secret_access_key": "", "s3_access_key_id": ""})

    assert "S3_BUCKET is set, so photos go to S3, which needs S3_ACCESS_KEY_ID" in message


def test_production_with_s3_keys_but_no_bucket_is_refused():
    message = errors_of(**{**PRODUCTION, "s3_bucket": ""})

    assert "is set while S3_BUCKET is empty" in message


@pytest.mark.parametrize(
    ("key", "value", "name"),
    [
        ("s3_access_key_id", "AKIAEXAMPLE", "S3_ACCESS_KEY_ID"),
        ("s3_secret_access_key", "s3-secret-value", "S3_SECRET_ACCESS_KEY"),
        ("s3_endpoint_url", "https://s3.gra.example.net", "S3_ENDPOINT_URL"),
        ("s3_public_base_url", "https://media.tabsira.me", "S3_PUBLIC_BASE_URL"),
    ],
)
def test_auto_refuses_s3_settings_without_a_bucket_instead_of_using_the_disk(key, value, name):
    assert f"{name} is set while S3_BUCKET is empty" in errors_of(**{key: value})


def test_an_explicit_local_backend_may_keep_the_s3_settings_for_later(make_settings):
    settings = make_settings(storage_backend="local", s3_access_key_id="AKIAEXAMPLE")

    assert settings.resolved_storage_backend == "local"


def test_a_complete_s3_configuration_is_accepted_and_tidied(make_settings):
    settings = make_settings(
        **{
            **S3,
            "s3_endpoint_url": " https://s3.gra.example.net/ ",
            "s3_bucket": " tabsira-photos ",
        }
    )

    assert settings.s3_public_base_url == "https://media.tabsira.me"
    assert settings.s3_endpoint_url == "https://s3.gra.example.net"
    assert settings.s3_bucket == "tabsira-photos"


def test_the_s3_secret_is_a_secret(make_settings):
    settings = make_settings(**S3)

    assert "s3-secret-value" not in repr(settings) + settings.model_dump_json()


@pytest.mark.parametrize("key", ["s3_endpoint_url", "s3_public_base_url"])
@pytest.mark.parametrize(
    "value",
    [
        "ftp://media.example",
        "media.example",
        "https://",
        "https://m.example/a?x=1",
        "https://m.example/#a",
        "https://owner:secret@m.example",
    ],
)
def test_an_s3_address_is_an_http_url_without_query_or_fragment(key, value):
    assert key.upper() in errors_of(**{key: value})


@pytest.mark.parametrize("seconds", [0, 29, 3601])
def test_a_signed_link_lives_between_half_a_minute_and_an_hour(seconds):
    assert "SIGNED_URL_TTL_SECONDS" in errors_of(signed_url_ttl_seconds=seconds)


def test_production_refuses_a_development_public_media_address():
    message = errors_of(**{**PRODUCTION, **S3, "s3_public_base_url": "https://media.tabsira.test"})

    assert "S3_PUBLIC_BASE_URL points at the development host https://media.tabsira.test" in message


def test_production_accepts_a_real_s3_configuration(make_settings):
    assert make_settings(**{**PRODUCTION, **S3}).storage_backend == "s3"


# ─── Admin area ────────────────────────────────────────────────────


def test_the_admin_settings_have_safe_defaults(make_settings):
    settings = make_settings()

    assert settings.feature_admin is True
    assert settings.admin_require_two_factor is False
    assert settings.admin_audit_retention_days == 400
    assert settings.admin_audit_compress_after_days == 30
    assert settings.admin_totp_encryption_key.get_secret_value() == ""


def test_an_empty_totp_key_derives_one_from_the_hash_key_and_a_set_one_wins(make_settings):
    derived = make_settings(hash_secret="one-secret-of-the-installation").admin_totp_keys
    other = make_settings(hash_secret="another-secret-of-the-installation").admin_totp_keys
    configured = make_settings(admin_totp_encryption_key=f" {FERNET_KEY} , {OTHER_FERNET_KEY},")

    # Each is a Fernet key, and the derivation depends on the installation's secret.
    assert len(derived) == 1
    assert derived != other
    assert configured.admin_totp_keys == (FERNET_KEY.encode(), OTHER_FERNET_KEY.encode())


@pytest.mark.parametrize("bad", ["not-a-key", "AAECAwQ=", f"{FERNET_KEY},oops"])
def test_a_totp_key_that_is_not_a_fernet_key_is_refused_without_being_echoed(bad):
    message = errors_of(admin_totp_encryption_key=bad)

    assert "ADMIN_TOTP_ENCRYPTION_KEY: must hold one or more Fernet keys" in message
    assert bad not in message


def test_compression_must_start_before_the_retention_ends():
    message = errors_of(admin_audit_retention_days=60, admin_audit_compress_after_days=60)

    assert "ADMIN_AUDIT_COMPRESS_AFTER_DAYS must be under ADMIN_AUDIT_RETENTION_DAYS" in message
    assert "ADMIN_AUDIT_RETENTION_DAYS" in errors_of(admin_audit_retention_days=29)


def test_production_refuses_the_admin_without_an_encryption_key_but_not_when_it_is_off(
    make_settings,
):
    without_key = {**PRODUCTION, "admin_totp_encryption_key": ""}

    assert "ADMIN_TOTP_ENCRYPTION_KEY is empty while FEATURE_ADMIN is on" in errors_of(
        **without_key
    )
    assert make_settings(**without_key, feature_admin=False).feature_admin is False


def test_the_social_guard_defaults_leave_a_band_for_a_person_to_review(make_settings):
    settings = make_settings()

    assert settings.social_guard_allow_score < settings.social_guard_reject_score
    assert settings.social_guard_timeout_seconds == 8.0
    assert settings.social_report_hold_threshold == 3
    assert settings.moderation_log_retention_days == 730
    assert settings.moderation_log_compress_after_days == 30


def test_an_allow_score_at_or_over_the_reject_score_is_refused():
    message = errors_of(
        database_url=DATABASE_URL, social_guard_allow_score=0.9, social_guard_reject_score=0.9
    )

    assert "SOCIAL_GUARD_ALLOW_SCORE must be lower than SOCIAL_GUARD_REJECT_SCORE" in message


def test_the_moderation_log_compresses_before_it_drops():
    message = errors_of(
        database_url=DATABASE_URL,
        moderation_log_retention_days=60,
        moderation_log_compress_after_days=60,
    )

    assert (
        "MODERATION_LOG_COMPRESS_AFTER_DAYS must be under MODERATION_LOG_RETENTION_DAYS" in message
    )


def test_contact_addresses_and_legal_versions_default_to_the_published_ones(make_settings):
    settings = make_settings()

    assert settings.support_email == "support@tabsira.me"
    assert settings.privacy_email == "privacy@tabsira.me"
    assert settings.terms_version == "2026-10-04T20:00Z"
    assert settings.privacy_version == "2026-10-04T23:00Z"
    assert (
        settings.support_max_per_ip_per_hour,
        settings.support_max_per_address_per_hour,
        settings.support_max_per_hour,
    ) == (5, 3, 200)


def test_contact_addresses_must_be_addresses(make_settings):
    assert "SUPPORT_EMAIL" in errors_of(support_email="nobody")
    assert "PRIVACY_EMAIL" in errors_of(privacy_email=" ")
    assert make_settings(support_email=" help@tabsira.me ").support_email == "help@tabsira.me"


def test_only_arabic_is_supported_and_the_default_must_be_supported(make_settings):
    assert make_settings().supported_languages == ("ar",)
    assert make_settings(supported_languages="ar, en").supported_languages == ("ar", "en")
    assert make_settings(supported_languages=("ar",)).supported_languages == ("ar",)
    assert "DEFAULT_LANGUAGE" in errors_of(default_language="en")


# ─── Redis, guests, scans, chat, treasure and time series ──────────


def test_scan_workflow_defaults(make_settings):
    settings = make_settings()

    assert settings.redis_url == DEV_REDIS_URL == "redis://127.0.0.1:6379/0"
    assert settings.redis_password.get_secret_value() == ""
    assert settings.test_redis_url == ""
    assert settings.guest_cookie_name == "__Secure-tabsira_guest"
    assert settings.guest_ttl.days == 90
    assert settings.scan_engine is ScanEngine.PIPELINE
    assert settings.scan_job_timeout_seconds == 240.0
    assert (settings.scan_image_ttl_seconds, settings.scan_events_ttl_seconds) == (3600, 3600)
    # v2 §6: 12 seconds and three redirects for a photo given by its address.
    assert (settings.image_url_timeout_seconds, settings.image_url_max_redirects) == (12.0, 3)
    assert settings.max_chat_user_messages == 3
    assert (settings.treasure_reveal_after_days, settings.treasure_return_after_hours) == (3, 12)
    assert (settings.scan_events_compress_after_days, settings.scan_events_retention_days) == (
        7,
        90,
    )
    assert (settings.ai_calls_compress_after_days, settings.ai_calls_retention_days) == (30, 400)
    assert (
        settings.evidence_exposures_compress_after_days,
        settings.evidence_exposures_retention_days,
    ) == (30, 730)


def test_the_redis_password_goes_into_the_client_url_only(make_settings):
    settings = make_settings(redis_url="rediss://10.0.0.5:6380/2", redis_password="p@ss/word")

    assert settings.redis_url == "rediss://10.0.0.5:6380/2"
    assert settings.redis_connection_url() == "rediss://:p%40ss%2Fword@10.0.0.5:6380/2"
    assert (
        settings.redis_connection_url("redis://127.0.0.1:6379/3")
        == "redis://:p%40ss%2Fword@127.0.0.1:6379/3"
    )
    assert make_settings().redis_connection_url() == DEV_REDIS_URL
    assert "p@ss" not in repr(settings)


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://127.0.0.1:6379/0", "redis://127.0.0.1:6379/0"),
        ("redis://localhost:6379/0", "not localhost"),
        ("redis://:pw@127.0.0.1:6379/0", "REDIS_PASSWORD"),
        ("redis://user@127.0.0.1:6379/0", "REDIS_PASSWORD"),
        ("redis://127.0.0.1:6379/zero", "database number"),
    ],
)
def test_redis_urls_are_checked(url, reason):
    assert reason in errors_of(redis_url=url)
    assert reason in errors_of(test_redis_url=url)


def test_the_tests_never_share_the_development_redis_database(make_settings):
    assert "TEST_REDIS_URL must name another database" in errors_of(
        redis_url="redis://127.0.0.1:6379/2", test_redis_url="redis://127.0.0.1:6379/2"
    )
    settings = make_settings(
        redis_url="redis://127.0.0.1:6379/2", test_redis_url=" redis://127.0.0.1:6379/3 "
    )
    assert settings.test_redis_url == "redis://127.0.0.1:6379/3"
    assert make_settings(test_redis_url="  ").test_redis_url == ""


def test_the_guest_cookie_name_follows_the_session_cookie_rules():
    assert "GUEST_COOKIE_NAME" in errors_of(guest_cookie_name="__Host-guest")


@pytest.mark.parametrize("series", ["scan_events", "ai_calls", "evidence_exposures"])
def test_a_time_series_is_compressed_before_it_is_dropped(series):
    message = errors_of(**{f"{series}_compress_after_days": 30, f"{series}_retention_days": 30})

    assert f"{series.upper()}_COMPRESS_AFTER_DAYS must be under" in message


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("guest_ttl_days", 0),
        ("scan_job_timeout_seconds", 541),
        ("scan_image_ttl_seconds", 59),
        ("scan_events_ttl_seconds", 86401),
        ("image_url_timeout_seconds", 0),
        ("image_url_max_redirects", 11),
        ("max_chat_user_messages", 11),
        ("treasure_reveal_after_days", -1),
        ("treasure_return_after_hours", 721),
        ("ai_calls_retention_days", 0),
    ],
)
def test_scan_workflow_numbers_have_bounds(key, value):
    assert key.upper() in errors_of(**{key: value})


def test_production_needs_a_redis_password_and_refuses_the_demo_engine():
    message = errors_of(**{**PRODUCTION, "redis_password": "", "scan_engine": "demo"})

    assert "REDIS_PASSWORD is empty" in message
    assert "SCAN_ENGINE is demo, a development simulation" in message


def test_an_embedding_size_left_empty_keeps_the_model_size(make_settings):
    empty = make_settings(ai_openai={"embedding_dimensions": ""})
    sized = make_settings(ai_ovh={"embedding_dimensions": "1024"})

    assert empty.ai_openai.embedding_dimensions is None
    assert sized.ai_ovh.embedding_dimensions == 1024
    with pytest.raises(ValidationError):
        make_settings(ai_openai={"embedding_dimensions": 3072})


def test_an_empty_reranker_url_switches_reranking_off(make_settings):
    assert make_settings(reranker="cross_encoder").reranker is RerankerKind.CROSS_ENCODER
    with pytest.raises(ValidationError):
        make_settings(reranker="cohere")
    assert make_settings(reranker_url=" ").reranker_url == ""
    assert (
        make_settings(reranker_url="http://127.0.0.1:8101/").reranker_url == "http://127.0.0.1:8101"
    )
    with pytest.raises(ValidationError):
        make_settings(reranker_url="vision:8100")


def test_cookies_are_secure_and_prefixed_only_where_the_web_app_is_served_over_https():
    """Local development runs over plain HTTP on port 80 (decision 49); production over https."""
    https = Settings(_env_file=None)
    http = Settings(
        _env_file=None,
        site_url="http://tabsira.test",
        api_url="http://api.tabsira.test",
        admin_url="http://admin.tabsira.test",
        cors_origins="http://tabsira.test",
    )

    assert https.cookie_secure is True
    assert https.cookie_name("__Secure-tabsira_session") == "__Secure-tabsira_session"
    assert http.cookie_secure is False
    assert http.cookie_name("__Secure-tabsira_session") == "tabsira_session"
    assert http.cookie_name("plain") == "plain"


@pytest.mark.parametrize("name", ["site_url", "api_url", "admin_url"])
def test_production_refuses_a_public_address_over_plain_http(name):
    message = errors_of(**{**PRODUCTION, name: "http://tabsira.me"})

    assert f"{name.upper()} must use https in production, not http://tabsira.me" in message


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("cors_origins", "https://tabsira.me,http://www.tabsira.me"),
        ("web_base_url", "http://tabsira.me"),
        ("google_redirect_uri", "http://api.tabsira.me/auth/google/callback"),
    ],
)
def test_production_refuses_every_other_public_address_over_plain_http(name, value):
    message = errors_of(**{**PRODUCTION, name: value})

    assert f"{name.upper()} must use https in production, not http://" in message


@pytest.mark.parametrize("name", ["session_cookie_name", "guest_cookie_name"])
def test_production_keeps_the_secure_prefix_on_the_cookie_names(name):
    message = errors_of(**{**PRODUCTION, name: "tabsira_plain"})

    assert f"{name.upper()} must start with __Secure- in production, not tabsira_plain" in message


def test_the_vector_archive_keys_are_typed_and_the_url_is_https(make_settings):
    settings = make_settings()
    local = make_settings(
        vectors_archive=" ../tabsira-data/vectors/x.tar.gz ", vectors_archive_url=" "
    )

    assert settings.vectors_archive == ""
    assert settings.vectors_archive_url.startswith("https://s3-v2.riastorage.com/tabsira/vectors/")
    assert local.vectors_archive == "../tabsira-data/vectors/x.tar.gz"
    assert local.vectors_archive_url == ""
    assert "VECTORS_ARCHIVE_URL" in errors_of(vectors_archive_url="http://example.org/v.tar.gz")


def test_the_corpus_archive_keys_are_typed_and_the_url_is_https(make_settings):
    settings = make_settings()
    local = make_settings(corpus_archive=" ../c.tar.gz ", corpus_archive_url=" ")

    assert settings.corpus_archive == ""
    assert settings.corpus_archive_url.startswith("https://s3-v2.riastorage.com/tabsira/corpus/")
    assert local.corpus_archive == "../c.tar.gz"
    assert local.corpus_archive_url == ""
    assert "CORPUS_ARCHIVE_URL must be an https address" in errors_of(
        corpus_archive_url="http://example.org/c.tar.gz"
    )


def test_geonames_installs_from_a_dump_only_when_one_is_named(make_settings):
    settings = make_settings()
    named = make_settings(
        geodata_dump=" ../g.dump ",
        geodata_dump_url=" https://s3-v2.riastorage.com/tabsira/geodata/g.dump ",
    )

    assert (settings.geodata_dump, settings.geodata_dump_url) == ("", "")
    assert named.geodata_dump == "../g.dump"
    assert named.geodata_dump_url == "https://s3-v2.riastorage.com/tabsira/geodata/g.dump"
    assert "GEODATA_DUMP_URL must be an https address" in errors_of(
        geodata_dump_url="ftp://example.org/g.dump"
    )


def test_geonames_comes_from_the_dump_unless_the_original_import_is_chosen(make_settings):
    assert make_settings().geonames_source is GeonamesSource.DUMP
    assert make_settings(geonames_source="geonames").geonames_source is GeonamesSource.GEONAMES
    assert "GEONAMES_SOURCE: Input should be 'dump' or 'geonames'" in errors_of(
        geonames_source="osm"
    )
