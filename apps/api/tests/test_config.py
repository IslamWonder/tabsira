from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src import config
from src.config import (
    AiProvider,
    AiStage,
    BoxCoordinates,
    ConfigError,
    Environment,
    ProviderSettings,
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
    "session_cookie_domain": ".tabsira.me",
    "hash_secret": "not-a-real-secret-but-long-enough-for-the-rule",
    "ai_provider": "ovh",
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


def test_ai_defaults_are_what_the_benchmark_measured(make_settings):
    settings = make_settings()

    # docs/BENCHMARK.md, 4 October 2026: only the vision stage and the guard are measured.
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
    measured = {(AiProvider.OVH, AiStage.VISION), (AiProvider.OPENAI, AiStage.VISION)}
    measured.add((AiProvider.OPENAI, AiStage.GUARD))
    for provider, block in (
        (AiProvider.OVH, settings.ai_ovh),
        (AiProvider.OPENAI, settings.ai_openai),
    ):
        for stage in AiStage:
            if (provider, stage) not in measured:
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
