"""
Typed application settings.

One `Settings` class holds every configuration key. It is read from the process
environment and from the root `.env`, and validated when the application builds
it: a missing or invalid key stops startup with a message that names the key.
Secrets are `SecretStr`, so printing or logging a `Settings` never shows them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from datetime import timedelta
from email.utils import parseaddr
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self
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
from sentry_sdk.utils import BadDsn, Dsn
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from src.geo.privacy import DEFAULT_CELL_METERS, MAX_CELL_METERS, MIN_CELL_METERS

# Process variable that replaces the .env lookup: a path to read instead, or an
# empty value to read no file at all. The test suite sets it so that a
# developer's real .env, with its keys and URLs, can never reach a test.
ENV_FILE_OVERRIDE = "TABSIRA_ENV_FILE"

# Where the services run when nothing else is configured: local development only.
DEV_SITE_URL = "https://tabsira.test"
DEV_API_URL = "https://api.tabsira.test"
DEV_ADMIN_URL = "https://admin.tabsira.test"

# Accounts. The cookie domain lets the web app and the API, on sibling subdomains,
# share the session; the .test value is development-only like the URLs above.
DEV_COOKIE_DOMAIN = ".tabsira.test"
DEV_GOOGLE_REDIRECT_URI = f"{DEV_API_URL}/auth/google/callback"
# Below this a production secret is refused; 32 characters is 190+ bits when random.
MIN_HASH_SECRET_LENGTH = 32
# The bcrypt work factor production must not go under.
MIN_PRODUCTION_BCRYPT_ROUNDS = 12

# Admin area. The audit log is a hypertable: it keeps this many days, and the chunks
# older than the second value are compressed. A Fernet key is 32 random bytes.
DEFAULT_AUDIT_RETENTION_DAYS = 400
DEFAULT_AUDIT_COMPRESS_AFTER_DAYS = 30
FERNET_KEY_BYTES = 32

# Where transactional mail says it comes from. The sending domain is the real one
# in development too: .test is not a mail domain.
DEFAULT_MAIL_FROM = "تبصرة <no-reply@tabsira.me>"
DEFAULT_SUPPORT_EMAIL = "support@tabsira.me"
DEFAULT_PRIVACY_EMAIL = "privacy@tabsira.me"
# The date the first terms and privacy texts were written.
DEFAULT_LEGAL_VERSION = "2026-10-04"
DEFAULT_LANGUAGE = "ar"

# A cookie name: RFC 6265 token characters we actually use. `__Host-` is refused
# because it forbids the Domain attribute that sharing the cookie needs.
_COOKIE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_COOKIE_DOMAIN = re.compile(r"^\.?[a-z0-9-]+(\.[a-z0-9-]+)+$")

# What the sitemap protocol allows in one file.
MAX_SITEMAP_PAGE_SIZE = 50_000

OVH_BASE_URL = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"

# The moderation log's retention and compression, in days, as they are before anyone sets them.
DEFAULT_MODERATION_RETENTION_DAYS = 730
DEFAULT_MODERATION_COMPRESS_AFTER_DAYS = 30

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


class BoxCoordinates(StrEnum):
    """
    How a provider's vision model writes the corners of a box.

    The prompt states the system and the server converts the answer to 0-1
    ratios. Qwen-VL models are trained on a 0-1000 grid and drift back to it
    even when asked for pixels; docs/BENCHMARK.md has the measurement.
    """

    PIXELS = "pixels"
    THOUSANDTHS = "thousandths"


class ConfigError(RuntimeError):
    """The configuration is missing a key or holds an invalid one."""


# AGENTS.md: gpt-oss models are never used, whatever the provider offers.
FORBIDDEN_MODEL_MARKERS = ("gpt-oss", "gpt_oss", "gptoss")


def refuse_forbidden_model(model: str) -> str:
    """Return `model`, or raise ValueError when it belongs to a forbidden family."""
    if any(marker in model.lower() for marker in FORBIDDEN_MODEL_MARKERS):
        message = f"{model} is a gpt-oss model, which this project never uses"
        raise ValueError(message)
    return model


# A provider's `reasoning_effort` values; empty sends none and leaves its default.
ReasoningEffort = Annotated[str, Field(pattern=r"^(|none|minimal|low|medium|high|xhigh)$")]


class ModelPrice(BaseModel):
    """What a model costs, in US dollars per million tokens."""

    model_config = ConfigDict(extra="forbid")

    input: Annotated[float, Field(ge=0)]
    output: Annotated[float, Field(ge=0)] = 0.0
    # Input tokens served from the provider's prompt cache; None when it has no discount.
    cached_input: Annotated[float, Field(ge=0)] | None = None


# Prices as of 4 October 2026 (docs/research/ai-providers.md): OVH from its
# /v1/models endpoint, OpenAI from its pricing page.
OVH_PRICES = {
    "Qwen3.8-27B": ModelPrice(input=0.47, output=3.19),
    "Qwen3.6-27B": ModelPrice(input=0.47, output=3.19),
    "Qwen3.5-397B-A17B": ModelPrice(input=0.71, output=4.25),
    "Qwen3.5-9B": ModelPrice(input=0.12, output=0.18),
    "Qwen2.5-VL-72B-Instruct": ModelPrice(input=1.01, output=1.01),
    "bge-m3": ModelPrice(input=0.01),
    "Qwen3-Embedding-8B": ModelPrice(input=0.12),
    "Qwen3Guard-Gen-8B": ModelPrice(input=0.0),
    "Qwen3Guard-Gen-0.6B": ModelPrice(input=0.0),
}
OPENAI_PRICES = {
    "gpt-5.4-mini-2026-03-17": ModelPrice(input=0.75, output=4.5, cached_input=0.075),
    "gpt-5.4-nano-2026-03-17": ModelPrice(input=0.2, output=1.25, cached_input=0.02),
    "text-embedding-3-small": ModelPrice(input=0.02),
    "text-embedding-3-large": ModelPrice(input=0.13),
    "omni-moderation-latest": ModelPrice(input=0.0),
}


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
    # Sent as `reasoning_effort` when set; empty leaves the provider's default.
    reasoning_effort: ReasoningEffort = ""
    # The coordinate system the vision prompt asks for and the server converts from.
    box_coordinates: BoxCoordinates = BoxCoordinates.PIXELS
    # Price of each model, keyed by model id; a model without a price is recorded with no cost.
    prices: dict[str, ModelPrice] = Field(default_factory=dict)

    @field_validator(
        "vision_model",
        "planner_model",
        "rerank_model",
        "verify_model",
        "compose_model",
        "chat_model",
        "embedding_model",
        "guard_model",
    )
    @classmethod
    def _refuse_forbidden_models(cls, value: str) -> str:
        return refuse_forbidden_model(value)

    @field_validator("prices")
    @classmethod
    def _refuse_forbidden_prices(cls, value: dict[str, ModelPrice]) -> dict[str, ModelPrice]:
        for model in value:
            refuse_forbidden_model(model)
        return value

    def model_for(self, stage: AiStage) -> str:
        """Return the model configured for `stage`; empty when none is set yet."""
        return str(getattr(self, f"{stage.value}_model"))


class OvhSettings(ProviderSettings):
    """OVHcloud AI Endpoints (OpenAI-compatible API)."""

    base_url: str = OVH_BASE_URL
    # Measured by docs/BENCHMARK.md (4 October 2026): Qwen3.8-27B without thinking
    # (thinking added 36 s at p50 for no gain), boxes on its native 0-1000 grid.
    vision_model: str = "Qwen3.8-27B"
    reasoning_effort: ReasoningEffort = "none"
    box_coordinates: BoxCoordinates = BoxCoordinates.THOUSANDTHS
    prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(OVH_PRICES))


class OpenAISettings(ProviderSettings):
    """OpenAI."""

    base_url: str = OPENAI_BASE_URL
    # Measured by docs/BENCHMARK.md (4 October 2026): gpt-5.4-mini without
    # reasoning, pixel boxes, and the free image moderation as the guard.
    vision_model: str = "gpt-5.4-mini-2026-03-17"
    reasoning_effort: ReasoningEffort = "none"
    guard_model: str = "omni-moderation-latest"
    prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(OPENAI_PRICES))


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


def _domain_is_test(domain: str) -> bool:
    """Return whether a cookie domain is a reserved `.test` development domain."""
    host = domain.lstrip(".")
    return host == "test" or host.endswith(".test")


def _split_keys(raw: str) -> list[str]:
    """Return the comma-separated keys of a setting, trimmed, without the empty ones."""
    return [key.strip() for key in raw.split(",") if key.strip()]


def _is_fernet_key(key: str) -> bool:
    """Whether `key` is 32 bytes as url-safe base64: what a Fernet key is."""
    try:
        return len(base64.urlsafe_b64decode(key.encode())) == FERNET_KEY_BYTES
    except (binascii.Error, ValueError):
        return False


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
    # Where the admin area (/admin) is served: its own host, reachable through the VPN only.
    # The /admin mount answers requests for this host and no other, and its state-changing
    # requests are accepted from this origin alone.
    admin_url: str = DEV_ADMIN_URL
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

    # Sessions. The cookie is always httpOnly, Secure and SameSite=Lax; only its
    # name, its domain and its lifetime are configurable.
    session_cookie_name: str = "__Secure-tabsira_session"
    session_cookie_domain: str = DEV_COOKIE_DOMAIN
    session_ttl_days: Annotated[int, Field(ge=1, le=365)] = 30

    # Key of the keyed hashes (HMAC-SHA256) of IP addresses and e-mail addresses
    # kept for rate limiting and sessions. Required in production; empty
    # elsewhere derives a per-installation key from DATABASE_URL.
    hash_secret: SecretStr = SecretStr("")
    # bcrypt work factor. Tests lower it; production may not go under 12.
    password_bcrypt_rounds: Annotated[int, Field(ge=4, le=16)] = 12

    # Admin area (/admin, decision 14), mounted only while FEATURE_ADMIN is on. The
    # second-factor secrets are encrypted at rest with these Fernet keys, comma
    # separated: the first encrypts, every one decrypts, so a key is rotated by putting
    # the new one first. Required in production when the admin is on; elsewhere empty
    # derives a key from HASH_SECRET.
    admin_totp_encryption_key: SecretStr = SecretStr("")
    # Whether an admin who has not enrolled the second factor may use the admin area
    # at all: when true, they can only reach the page that enrols it.
    admin_require_two_factor: bool = False
    # The audit log keeps this many days, and compresses chunks older than the second value.
    admin_audit_retention_days: Annotated[int, Field(ge=30, le=3650)] = DEFAULT_AUDIT_RETENTION_DAYS
    admin_audit_compress_after_days: Annotated[int, Field(ge=1, le=365)] = (
        DEFAULT_AUDIT_COMPRESS_AFTER_DAYS
    )

    # Rate limiting of sign-in and sign-up, kept in PostgreSQL.
    auth_attempt_window_seconds: Annotated[int, Field(ge=1)] = 900
    auth_max_attempts_per_ip: Annotated[int, Field(ge=1)] = 20
    auth_max_attempts_per_email: Annotated[int, Field(ge=1)] = 5

    # Google sign-in (OpenID Connect, authorization code flow with PKCE). An
    # empty client id turns it off: its routes then answer 503.
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = DEV_GOOGLE_REDIRECT_URI
    google_state_ttl_seconds: Annotated[int, Field(ge=30, le=3600)] = 600

    # Transactional mail (verification, password reset), sent by the API over
    # SMTP, always encrypted. While SMTP_HOST is empty nothing is sent: the
    # endpoints answer as usual and the API logs an error.
    smtp_host: str = ""
    smtp_port: Annotated[int, Field(ge=1, le=65535)] = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    # starttls (port 587 or 25) or ssl (port 465); never clear text.
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    # Only for a server that a private certificate authority signed.
    smtp_ca_file: str = ""
    smtp_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 15.0
    mail_from: str = DEFAULT_MAIL_FROM
    mail_reply_to: str = ""
    # Base of the links in mail. Empty uses SITE_URL.
    web_base_url: str = ""
    email_verification_expire_hours: Annotated[int, Field(ge=1, le=168)] = 24
    password_reset_expire_minutes: Annotated[int, Field(ge=5, le=1440)] = 60

    # Contact addresses named on the terms and privacy pages (decision 34): the
    # support form mails SUPPORT_EMAIL.
    support_email: str = DEFAULT_SUPPORT_EMAIL
    privacy_email: str = DEFAULT_PRIVACY_EMAIL
    # Versions of the terms of use and the privacy policy. Changing one asks every
    # account to accept again (decision 35).
    terms_version: Annotated[str, Field(min_length=1, max_length=32)] = DEFAULT_LEGAL_VERSION
    privacy_version: Annotated[str, Field(min_length=1, max_length=32)] = DEFAULT_LEGAL_VERSION
    # Limits of the support form, per hashed address and over all addresses, in each worker.
    support_max_per_address_per_hour: Annotated[int, Field(ge=1)] = 5
    support_max_per_hour: Annotated[int, Field(ge=1)] = 200
    # Language readiness (decision 36): Arabic only today; every text is keyed by language.
    default_language: str = DEFAULT_LANGUAGE
    supported_languages: Annotated[tuple[str, ...], NoDecode] = (DEFAULT_LANGUAGE,)

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

    # Side, in metres, of the grid cell a public location is rounded to (see
    # src/geo/privacy.py). The limits are the ones that function enforces.
    geo_approx_cell_meters: Annotated[float, Field(ge=MIN_CELL_METERS, le=MAX_CELL_METERS)] = (
        DEFAULT_CELL_METERS
    )

    # Error tracking: GlitchTip, which speaks the Sentry protocol. An empty DSN
    # turns it off, and then no code path sends anything. The web DSN is the
    # project that receives what browsers post to /client-errors; empty sends
    # those to the API project, so one DSN is enough.
    glitchtip_dsn: SecretStr = SecretStr("")
    glitchtip_web_dsn: SecretStr = SecretStr("")
    # Share of requests timed as well as errors; 0 keeps it to errors only.
    glitchtip_traces_sample_rate: Annotated[float, Field(ge=0, le=1)] = 0.0
    # Version part of the release name, for a checkout git cannot describe.
    glitchtip_release: Annotated[str, Field(pattern=r"^[A-Za-z0-9._+-]{0,100}$")] = ""

    # Cookie consent (decision 32). The version names the current text of the cookie
    # policy: raising it, because the text changed, asks every visitor again. A
    # choice also lapses after CONSENT_REASK_DAYS (six months by default).
    cookie_policy_version: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,32}$")] = "2026-10-04"
    consent_reask_days: Annotated[int, Field(ge=1, le=730)] = 182

    # The most URLs one page of the sitemap holds. The protocol allows 50,000; a lower
    # number keeps each page cheap to build and stable (a new record changes only the
    # last page of its section).
    sitemap_page_size: Annotated[int, Field(ge=1, le=MAX_SITEMAP_PAGE_SIZE)] = 10_000

    # Where consented photos are kept (decisions 8 and 19): on local disk under
    # data/media in development, in a private S3-compatible bucket in production.
    # Every S3 key below is required once the backend is "s3", in any environment.
    storage_backend: Literal["local", "s3"] = "local"
    # Empty uses AWS; set it for another S3-compatible service.
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = SecretStr("")
    # Where the public/ prefix of the bucket is served from: a CDN or the bucket's own
    # public address. Only photos their owner published are ever under that prefix.
    s3_public_base_url: str = ""
    # Seconds a signed link to a private photo stays valid. Short on purpose.
    signed_url_ttl_seconds: Annotated[int, Field(ge=30, le=3600)] = 300

    # AI providers: one active provider, one settings block each. In the
    # environment the blocks are AI_OVH__API_KEY, AI_OPENAI__VISION_MODEL, ...
    # OpenAI by measurement (docs/BENCHMARK.md): same quality as OVH's best on the
    # gold scenes, scene analysis p95 5.7 s against 27 s.
    ai_provider: AiProvider = AiProvider.OPENAI
    ai_ovh: OvhSettings = OvhSettings()
    ai_openai: OpenAISettings = OpenAISettings()
    # Seconds one model request may take before it is abandoned (and retried).
    ai_timeout_seconds: Annotated[float, Field(gt=0)] = 90.0
    # Further attempts after a timeout, a network error, a 429, a 5xx or an
    # answer that does not match its schema. Bounded: a stage never loops.
    ai_max_retries: Annotated[int, Field(ge=0, le=5)] = 2
    # Wait before the first retry; doubled for each later one.
    ai_retry_backoff_seconds: Annotated[float, Field(ge=0)] = 1.0

    # The object detector (services/vision), reached over HTTP only. A detector
    # that does not answer in time is skipped and the scan goes on without boxes.
    detector_url: str = "http://127.0.0.1:8100"
    detector_timeout_seconds: Annotated[float, Field(gt=0)] = 30.0

    # Photos received for a scan: largest upload, and largest decoded size
    # (checked from the header, before decoding: a small file can expand a lot).
    image_max_bytes: Annotated[int, Field(gt=0)] = 15 * 1024 * 1024
    image_max_pixels: Annotated[int, Field(gt=0)] = 40_000_000

    # The social network's automatic guard. Text goes to OpenAI's moderation endpoint
    # (the free `omni-moderation-latest`) and the verdict is read from its scores:
    # under the allow score the item is published, over the reject score it is
    # refused, anything between (or any failure of the call) waits for a person.
    social_guard_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 8.0
    social_guard_allow_score: Annotated[float, Field(ge=0, lt=1)] = 0.4
    social_guard_reject_score: Annotated[float, Field(gt=0, le=1)] = 0.85
    # Distinct accounts that report one published post or comment before it goes back
    # to the moderation queue, hidden until a person decides. 0 turns this off.
    social_report_hold_threshold: Annotated[int, Field(ge=0, le=100)] = 3
    # The moderation log is a TimescaleDB hypertable (decision 13): chunks older than
    # the retention are dropped, chunks older than the compression age are compressed.
    moderation_log_retention_days: Annotated[int, Field(ge=30, le=3650)] = (
        DEFAULT_MODERATION_RETENTION_DAYS
    )
    moderation_log_compress_after_days: Annotated[int, Field(ge=1, le=365)] = (
        DEFAULT_MODERATION_COMPRESS_AFTER_DAYS
    )

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

    @field_validator("site_url", "api_url", "admin_url")
    @classmethod
    def _check_public_url(cls, value: str) -> str:
        return _origin(value)

    @field_validator("session_cookie_name")
    @classmethod
    def _check_cookie_name(cls, value: str) -> str:
        if not _COOKIE_NAME.match(value) or value.startswith("__Host-"):
            message = "must be 1 to 64 letters, digits, dots, dashes or underscores, not __Host-"
            raise ValueError(message)
        return value

    @field_validator("session_cookie_domain")
    @classmethod
    def _check_cookie_domain(cls, value: str) -> str:
        domain = value.strip().lower()
        if domain and not _COOKIE_DOMAIN.match(domain):
            message = "must be a domain such as .tabsira.me, or empty for a host-only cookie"
            raise ValueError(message)
        return domain

    @field_validator("mail_from", "mail_reply_to")
    @classmethod
    def _check_mail_address(cls, value: str) -> str:
        if value and "@" not in parseaddr(value)[1]:
            message = 'must be an address, with or without a name: "Name <a@example.com>"'
            raise ValueError(message)
        return value.strip()

    @field_validator("support_email", "privacy_email")
    @classmethod
    def _check_contact_address(cls, value: str) -> str:
        address = value.strip()
        if not address or "@" not in parseaddr(address)[1]:
            message = "must be an e-mail address"
            raise ValueError(message)
        return address

    @field_validator("supported_languages", mode="before")
    @classmethod
    def _split_languages(cls, value: Any) -> Any:
        """Accept the comma-separated form an environment variable can carry."""
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @model_validator(mode="after")
    def _default_language_is_supported(self) -> Self:
        if self.default_language not in self.supported_languages:
            message = "DEFAULT_LANGUAGE must be one of SUPPORTED_LANGUAGES"
            raise ValueError(message)
        return self

    @field_validator("web_base_url")
    @classmethod
    def _check_web_base_url(cls, value: str) -> str:
        return _origin(value) if value.strip() else ""

    @field_validator("smtp_ca_file")
    @classmethod
    def _check_ca_file(cls, value: str) -> str:
        if value and not Path(value).is_file():
            message = "must be the path of an existing file"
            raise ValueError(message)
        return value

    @field_validator("admin_totp_encryption_key")
    @classmethod
    def _check_totp_keys(cls, value: SecretStr) -> SecretStr:
        """Every comma-separated key must be a Fernet key; never echo one back."""
        raw = value.get_secret_value()
        if raw and not all(_is_fernet_key(key) for key in _split_keys(raw)):
            message = (
                "must hold one or more Fernet keys (32 random bytes as url-safe base64), "
                "comma separated"
            )
            raise ValueError(message)
        return value

    @field_validator("google_client_id")
    @classmethod
    def _strip_client_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("google_redirect_uri")
    @classmethod
    def _check_redirect_uri(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.fragment:
            message = "must be an http(s) URL with a host and no fragment"
            raise ValueError(message)
        return value.strip()

    @field_validator("detector_url")
    @classmethod
    def _check_detector_url(cls, value: str) -> str:
        return _origin(value)

    @field_validator("glitchtip_dsn", "glitchtip_web_dsn")
    @classmethod
    def _check_glitchtip_dsn(cls, value: SecretStr) -> SecretStr:
        """Accept an empty DSN (off) or one the Sentry SDK can read; never echo it."""
        dsn = value.get_secret_value().strip()
        if dsn:
            try:
                Dsn(dsn)
            except BadDsn:
                message = "must be empty or a DSN of the form https://key@host/project-id"
                raise ValueError(message) from None
        return SecretStr(dsn)

    @field_validator("s3_endpoint_url", "s3_public_base_url")
    @classmethod
    def _check_s3_url(cls, value: str) -> str:
        """Accept an empty address, or an http(s) one with a host and no query or fragment."""
        candidate = value.strip()
        if not candidate:
            return ""
        parts = urlsplit(candidate)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            message = "must be empty or an http(s) URL with a host"
            raise ValueError(message)
        if parts.query or parts.fragment:
            message = "must have no query and no fragment"
            raise ValueError(message)
        return candidate.rstrip("/")

    @field_validator("s3_bucket", "s3_access_key_id", "s3_region")
    @classmethod
    def _strip_s3_text(cls, value: str) -> str:
        return value.strip()

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
    def _require_s3_settings(self) -> Self:
        """With the S3 backend every S3 key must be set, so photos are never lost to a typo."""
        if self.storage_backend != "s3":
            return self
        missing = [
            name.upper()
            for name in ("s3_bucket", "s3_access_key_id", "s3_public_base_url", "s3_region")
            if not getattr(self, name)
        ]
        if not self.s3_secret_access_key.get_secret_value():
            missing.append("S3_SECRET_ACCESS_KEY")
        if missing:
            message = "STORAGE_BACKEND=s3 needs " + ", ".join(missing)
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _check_audit_windows(self) -> Self:
        """Compression waits for part of the retention, never all of it."""
        if self.admin_audit_compress_after_days >= self.admin_audit_retention_days:
            message = "ADMIN_AUDIT_COMPRESS_AFTER_DAYS must be under ADMIN_AUDIT_RETENTION_DAYS"
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _guard_scores_leave_a_band_for_review(self) -> Self:
        """Keep the allow score under the reject score, or no item could ever wait for a person."""
        if self.social_guard_allow_score >= self.social_guard_reject_score:
            message = "SOCIAL_GUARD_ALLOW_SCORE must be lower than SOCIAL_GUARD_REJECT_SCORE"
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _check_moderation_log_windows(self) -> Self:
        """Compression waits for part of the retention, never all of it."""
        if self.moderation_log_compress_after_days >= self.moderation_log_retention_days:
            message = (
                "MODERATION_LOG_COMPRESS_AFTER_DAYS must be under MODERATION_LOG_RETENTION_DAYS"
            )
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> Self:
        """Stop a production process that still carries development values."""
        if self.environment != Environment.PRODUCTION:
            return self
        problems = self._production_problems()
        if problems:
            message = "Refusing to start with ENVIRONMENT=production: " + "; ".join(problems)
            raise ValueError(message)
        return self

    def _production_problems(self) -> list[str]:
        """List what makes these settings unfit for production."""
        problems = [
            f"{name} points at the development host {url}"
            for name, url in (
                [
                    ("SITE_URL", self.site_url),
                    ("API_URL", self.api_url),
                    ("ADMIN_URL", self.admin_url),
                    ("WEB_BASE_URL", self.web_base_url),
                    ("S3_PUBLIC_BASE_URL", self.s3_public_base_url),
                ]
                + [("CORS_ORIGINS", origin) for origin in self.cors_origins]
            )
            if _host_is_test_domain(url)
        ]
        if not self.ai.api_key.get_secret_value():
            problems.append(f"the key of the active AI provider ({self.ai_provider}) is empty")
        if _domain_is_test(self.session_cookie_domain):
            problems.append(
                f"SESSION_COOKIE_DOMAIN is the development domain {self.session_cookie_domain}"
            )
        if len(self.hash_secret.get_secret_value()) < MIN_HASH_SECRET_LENGTH:
            problems.append(f"HASH_SECRET must hold at least {MIN_HASH_SECRET_LENGTH} characters")
        if self.password_bcrypt_rounds < MIN_PRODUCTION_BCRYPT_ROUNDS:
            problems.append(f"PASSWORD_BCRYPT_ROUNDS is under {MIN_PRODUCTION_BCRYPT_ROUNDS}")
        for name, dsn in (
            ("GLITCHTIP_DSN", self.glitchtip_dsn),
            ("GLITCHTIP_WEB_DSN", self.glitchtip_web_dsn),
        ):
            if dsn.get_secret_value() and _host_is_test_domain(dsn.get_secret_value()):
                problems.append(f"{name} points at a development host")
        if self.feature_admin and not self.admin_totp_encryption_key.get_secret_value():
            problems.append(
                "ADMIN_TOTP_ENCRYPTION_KEY is empty while FEATURE_ADMIN is on "
                "(set a key, or turn the admin area off)"
            )
        if self.google_configured:
            if not self.google_client_secret.get_secret_value():
                problems.append("GOOGLE_CLIENT_ID is set but GOOGLE_CLIENT_SECRET is empty")
            if _host_is_test_domain(self.google_redirect_uri):
                problems.append(
                    f"GOOGLE_REDIRECT_URI points at the development host {self.google_redirect_uri}"
                )
        return problems

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def google_configured(self) -> bool:
        """Whether Google sign-in is switched on: it needs a client id."""
        return bool(self.google_client_id)

    @property
    def glitchtip_configured(self) -> bool:
        """Whether errors are reported: only with a DSN."""
        return bool(self.glitchtip_dsn.get_secret_value())

    @property
    def glitchtip_web_dsn_value(self) -> str:
        """The DSN browser reports go to: the web project's, else the API project's; empty is off."""
        return self.glitchtip_web_dsn.get_secret_value() or self.glitchtip_dsn.get_secret_value()

    @property
    def consent_reask(self) -> timedelta:
        """How long a cookie-consent choice stays in force."""
        return timedelta(days=self.consent_reask_days)

    @property
    def session_ttl(self) -> timedelta:
        return timedelta(days=self.session_ttl_days)

    @property
    def smtp_configured(self) -> bool:
        """Whether mail can be sent: a server and a sender are set."""
        return bool(self.smtp_host and self.mail_from)

    @property
    def mail_link_base(self) -> str:
        """Base of the links in mail: WEB_BASE_URL, else the web app's own address."""
        return self.web_base_url or self.site_url

    @property
    def admin_host(self) -> str:
        """The host (lower case, with its port when ADMIN_URL has one) the admin area answers to."""
        return urlsplit(self.admin_url).netloc.lower()

    @property
    def allowed_origins(self) -> frozenset[str]:
        """Origins a browser may send state-changing requests from: the web app and this API."""
        return frozenset([*self.cors_origins, self.api_url])

    @property
    def hash_key(self) -> bytes:
        """
        Key of the keyed hashes of IP and e-mail addresses.

        Production must set HASH_SECRET. Elsewhere an empty one derives a key
        from DATABASE_URL, which already holds this installation's random
        password, so no secret is written in the source.
        """
        secret = self.hash_secret.get_secret_value()
        if secret:
            return secret.encode()
        derived = hashlib.sha256(
            b"tabsira-hash-key:" + self.database_url.get_secret_value().encode()
        )
        return derived.digest()

    @property
    def admin_totp_keys(self) -> tuple[bytes, ...]:
        """
        The Fernet keys that protect the second-factor secrets, the encrypting one first.

        Production must set ADMIN_TOTP_ENCRYPTION_KEY. Elsewhere an empty one derives a
        key from `hash_key`, so a development database needs no extra secret.
        """
        configured = _split_keys(self.admin_totp_encryption_key.get_secret_value())
        if configured:
            return tuple(key.encode() for key in configured)
        derived = hashlib.sha256(b"tabsira-admin-totp-key:" + self.hash_key).digest()
        return (base64.urlsafe_b64encode(derived),)

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
