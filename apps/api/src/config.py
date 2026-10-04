"""
Typed application settings.

One `Settings` class holds every configuration key. It is read from the process
environment and from the root `.env`, and validated when the application builds
it: a missing or invalid key stops startup with a message that names the key.
Secrets are `SecretStr`, so printing or logging a `Settings` never shows them.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# Process variable that replaces the .env lookup: a path to read instead, or an
# empty value to read no file at all. The test suite sets it so that a
# developer's real .env, with its keys and URLs, can never reach a test.
ENV_FILE_OVERRIDE = "TABSIRA_ENV_FILE"

# Where the services run when nothing else is configured: local development only.
DEV_SITE_URL = "https://tabsira.test"
DEV_API_URL = "https://api.tabsira.test"

OVH_BASE_URL = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"

ASYNC_DRIVER = "postgresql+asyncpg"
SYNC_DRIVER = "postgresql+psycopg"


class Environment(StrEnum):
    """
    The environment the API runs in.

    Typed on purpose: several decisions compare it, and as a free string a typo
    such as `prodcution` would silently pick the permissive branch of each.
    """

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AiProvider(StrEnum):
    """The AI provider that serves every stage; switched by one setting."""

    OVH = "ovh"
    OPENAI = "openai"


class AiStage(StrEnum):
    """A pipeline stage that calls a model; each provider names one model per stage."""

    VISION = "vision"
    PLANNER = "planner"
    RERANK = "rerank"
    VERIFY = "verify"
    COMPOSE = "compose"
    CHAT = "chat"
    EMBEDDING = "embedding"
    GUARD = "guard"


class ConfigError(RuntimeError):
    """The configuration is missing a key or holds an invalid one."""


class ProviderSettings(BaseModel):
    """
    One AI provider: its endpoint, its key and the model of each stage.

    A model name stays empty until the benchmark has measured which model each
    stage should use. A key that is not a field is an error, not ignored: a
    typo in AI_OVH__VISON_MODEL must not leave a stage without its model.
    """

    model_config = ConfigDict(extra="forbid")

    base_url: str = ""
    api_key: SecretStr = SecretStr("")
    vision_model: str = ""
    planner_model: str = ""
    rerank_model: str = ""
    verify_model: str = ""
    compose_model: str = ""
    chat_model: str = ""
    embedding_model: str = ""
    guard_model: str = ""

    def model_for(self, stage: AiStage) -> str:
        """Return the model configured for `stage`; empty when none is set yet."""
        return str(getattr(self, f"{stage.value}_model"))


class OvhSettings(ProviderSettings):
    """OVHcloud AI Endpoints (OpenAI-compatible API)."""

    base_url: str = OVH_BASE_URL


class OpenAISettings(ProviderSettings):
    """OpenAI."""

    base_url: str = OPENAI_BASE_URL


def _env_files(here: Path) -> tuple[Path, ...]:
    """
    Return the .env paths to read for a module living at `here`.

    In a checkout this module sits at apps/api/src/config.py and the .env is at
    the repository root, three directories up. In a container the app is copied
    to /app and there is no such parent, so the parents that exist are used and
    the working directory's own .env is read last, where it wins.
    """
    override = os.environ.get(ENV_FILE_OVERRIDE)
    if override is not None:
        return (Path(override),) if override else ()
    ancestors = [parent / ".env" for parent in reversed(here.parents[:4])]
    return (*ancestors, Path(".env"))


def _origin(value: str) -> str:
    """Return `value` as a bare origin (scheme and host), or raise ValueError."""
    candidate = value.strip()
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        message = "must be an http(s) URL with a host"
        raise ValueError(message)
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        message = "must be a bare origin: scheme, host and optional port, no path"
        raise ValueError(message)
    return candidate.rstrip("/")


def _host_is_test_domain(url: str) -> bool:
    """Return whether `url` points at a reserved `.test` development host."""
    host = urlsplit(url).hostname or ""
    return host == "test" or host.endswith(".test")


def _check_postgres_url(value: SecretStr, driver: str) -> SecretStr:
    """Validate a database URL without ever echoing it back in an error."""
    try:
        url = make_url(value.get_secret_value())
    except ArgumentError:
        message = f"must be a URL of the form {driver}://user:password@127.0.0.1:5432/name"
        raise ValueError(message) from None
    if url.drivername != driver:
        message = f"must use the {driver} driver"
        raise ValueError(message)
    if url.host == "localhost":
        message = "must name the host 127.0.0.1, not localhost"
        raise ValueError(message)
    if not url.host or not url.database:
        message = "must include a host and a database name"
        raise ValueError(message)
    return value


class Settings(BaseSettings):
    """Every configuration key of the API, with its development default."""

    model_config = SettingsConfigDict(
        env_file=_env_files(Path(__file__).resolve()),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        # The root .env also carries the keys of the web app and of the scripts.
        extra="ignore",
        # A failed validation must never echo a value: it may be a password.
        hide_input_in_errors=True,
    )

    # Runtime
    environment: Environment = Environment.DEVELOPMENT
    # The address the API binds to: always loopback; nginx is the public face.
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Public addresses. The .test defaults are development-only (mkcert TLS) and
    # are refused in production.
    site_url: str = DEV_SITE_URL
    api_url: str = DEV_API_URL
    # Browser origins allowed to call the API, comma separated in the environment.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: [DEV_SITE_URL])

    # Database. Required: there is no default, because a default would carry a password.
    database_url: SecretStr
    # The same database over the psycopg driver, for tools that are not async.
    sync_database_url: SecretStr | None = None
    # The database tests run against; never the development one.
    test_database_url: SecretStr | None = None
    # Seconds to wait for a database connection before giving up. Short on
    # purpose: a database that is down must not hang the first page.
    db_connect_timeout: float = 3.0
    db_pool_size: int = 5
    db_max_overflow: int = 5

    # Feature flags. A feature that is off must not break the core journey.
    feature_chat: bool = True
    feature_world: bool = True
    feature_treasure: bool = True
    feature_social: bool = True
    feature_atlas: bool = True
    feature_camera_discovery: bool = True
    # Level C of the camera view (anchoring) stays off until it is proven on devices.
    feature_camera_anchor: bool = False
    feature_photo_storage: bool = True
    feature_canonical_verify: bool = True
    feature_admin: bool = True

    # AI providers: one active provider, one settings block each. In the
    # environment the blocks are AI_OVH__API_KEY, AI_OPENAI__VISION_MODEL, ...
    ai_provider: AiProvider = AiProvider.OVH
    ai_ovh: OvhSettings = OvhSettings()
    ai_openai: OpenAISettings = OpenAISettings()

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        """Accept the comma-separated form an environment variable can carry."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _check_origins(cls, value: list[str]) -> list[str]:
        return [_origin(origin) for origin in value]

    @field_validator("site_url", "api_url")
    @classmethod
    def _check_public_url(cls, value: str) -> str:
        return _origin(value)

    @field_validator("sync_database_url", "test_database_url", mode="before")
    @classmethod
    def _empty_means_unset(cls, value: Any) -> Any:
        """Treat a key left empty in the .env as a key that is not set."""
        return None if value == "" else value

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: SecretStr) -> SecretStr:
        return _check_postgres_url(value, ASYNC_DRIVER)

    @field_validator("sync_database_url")
    @classmethod
    def _check_sync_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        return value if value is None else _check_postgres_url(value, SYNC_DRIVER)

    @field_validator("test_database_url")
    @classmethod
    def _check_test_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        _check_postgres_url(value, ASYNC_DRIVER)
        if not (make_url(value.get_secret_value()).database or "").endswith("_test"):
            message = "must name a database ending in _test, so tests can never touch real data"
            raise ValueError(message)
        return value

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> Self:
        """Stop a production process that still carries development values."""
        if self.environment != Environment.PRODUCTION:
            return self

        problems = [
            f"{name} points at the development host {url}"
            for name, url in (
                [("SITE_URL", self.site_url), ("API_URL", self.api_url)]
                + [("CORS_ORIGINS", origin) for origin in self.cors_origins]
            )
            if _host_is_test_domain(url)
        ]
        if not self.ai.api_key.get_secret_value():
            problems.append(f"the key of the active AI provider ({self.ai_provider}) is empty")
        if problems:
            message = "Refusing to start with ENVIRONMENT=production: " + "; ".join(problems)
            raise ValueError(message)
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def ai(self) -> ProviderSettings:
        """The settings block of the active AI provider."""
        return self.ai_ovh if self.ai_provider == AiProvider.OVH else self.ai_openai


def format_validation_error(error: ValidationError) -> str:
    """
    Describe a failed validation in terms of environment variables.

    Only the key and the reason are printed, never the value that was given:
    it may be a password or an API key.
    """
    lines = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        key = "__".join(str(part) for part in item["loc"]).upper() or "SETTINGS"
        reason = item["msg"].removeprefix("Value error, ")
        lines.append(f"  - {key}: {reason}")
    return "Invalid configuration, fix the .env:\n" + "\n".join(lines)


def load_settings() -> Settings:
    """Read and validate the settings; raise `ConfigError` naming every bad key."""
    try:
        return Settings()
    except ValidationError as error:
        raise ConfigError(format_validation_error(error)) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return load_settings()
