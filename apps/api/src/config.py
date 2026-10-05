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
from collections.abc import Mapping
from datetime import timedelta
from email.utils import parseaddr
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from sentry_sdk.utils import BadDsn, Dsn
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from src.features import FeatureFlag, active_flags, legacy_advice, parse_flags
from src.geo.privacy import DEFAULT_CELL_METERS, MAX_CELL_METERS, MIN_CELL_METERS

# Process variable that replaces the .env lookup: a path to read instead, or an
# empty value to read no file at all. The test suite sets it so that a
# developer's real .env, with its keys and URLs, can never reach a test.
ENV_FILE_OVERRIDE = "TABSIRA_ENV_FILE"

# The development hosts, used when nothing else is configured (tests, CI). A
# developer's `.env`, written from `.env.example`, names them over plain HTTP on
# port 80 (decision 49); the https form here keeps the test suite on the cookie
# and origin rules production runs under. Production refuses `.test` and http.
DEV_SITE_URL = "http://tabsira.test"
DEV_API_URL = "http://api.tabsira.test"
DEV_ADMIN_URL = "http://admin.tabsira.test"

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
# Cloudflare's published dummy keys start with 1x (always pass), 2x (always fail), 3x (forced
# challenge). The site key shape is the one the web app accepts (apps/web/src/config/server-env.ts).
TURNSTILE_TEST_KEY_PREFIXES = ("1x", "2x", "3x")
TURNSTILE_SITE_KEY_PATTERN = re.compile(r"[0-9A-Za-z_-]{8,64}")
DEFAULT_LEGAL_VERSION = "2026-10-04T20:00Z"
# The privacy policy moved on when Cloudflare Turnstile joined the browser's third-party contacts.
DEFAULT_PRIVACY_VERSION = "2026-10-05T15:00Z"
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

# Redis on the development host (decision 21); the password, when there is one, is
# REDIS_PASSWORD, never part of the URL, so the URL can be printed.
DEV_REDIS_URL = "redis://127.0.0.1:6379/0"
REDIS_SCHEMES = frozenset({"redis", "rediss"})

# Retention and compression of the time series (decision 13), in days.
DEFAULT_SCAN_EVENTS_RETENTION_DAYS = 90
DEFAULT_SCAN_EVENTS_COMPRESS_AFTER_DAYS = 7
DEFAULT_AI_CALLS_RETENTION_DAYS = 400
DEFAULT_AI_CALLS_COMPRESS_AFTER_DAYS = 30
DEFAULT_EXPOSURES_RETENTION_DAYS = 730
DEFAULT_EXPOSURES_COMPRESS_AFTER_DAYS = 30


# The checkout's root is the first parent that holds the workspace file.
CHECKOUT_MARKER = "pnpm-workspace.yaml"


def checkout_root() -> Path:
    """Return the checkout's root; the working directory when this code runs outside one."""
    for parent in Path(__file__).resolve().parents:
        if (parent / CHECKOUT_MARKER).is_file():
            return parent
    return Path.cwd()


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


class GeonamesSource(StrEnum):
    """Where scripts/geodata/ensure.sh takes GeoNames from (decision 57)."""

    # The verified 2026-10-04 snapshot in the owners' bucket (GEODATA_DUMP, GEODATA_DUMP_URL).
    DUMP = "dump"
    # A fresh import from geonames.org with scripts/seed-geonames.sh: about 600 MB, 15 minutes.
    GEONAMES = "geonames"


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


class ScanEngine(StrEnum):
    """
    The insight engine a scan runs.

    `demo` is a declared simulation for development and smoke tests: it never
    calls a model, cites only references the store holds, and every insight it
    makes is labelled as coming from it. Production refuses it.
    """

    PIPELINE = "pipeline"
    DEMO = "demo"


class RerankerKind(StrEnum):
    """
    What reorders the head of the fused evidence candidates (decision 41).

    `llm` asks the provider's small text model (its rerank model) for a score per
    numbered candidate; a provider without one reranks nothing. `cross_encoder`
    calls services/vision at RERANKER_URL, for a host with a GPU. `off` keeps the
    fused order.
    """

    LLM = "llm"
    CROSS_ENCODER = "cross_encoder"
    OFF = "off"


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
    # Size asked of the embedding model (`dimensions`); None keeps the model's own size.
    embedding_dimensions: Annotated[int, Field(ge=1, le=2000)] | None = None
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

    @field_validator("embedding_dimensions", mode="before")
    @classmethod
    def _empty_dimensions_mean_native(cls, value: Any) -> Any:
        """Treat a key left empty in the .env as the model's own size."""
        return None if value == "" else value

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
    # Decision 46: the chat answers with the provider's insight-stage model.
    chat_model: str = "Qwen3.8-27B"
    # The text stages use the vision stage's model, without thinking: not measured
    # apart; docs/EVALUATION.md measures them on the OpenAI defaults.
    planner_model: str = "Qwen3.8-27B"
    verify_model: str = "Qwen3.8-27B"
    compose_model: str = "Qwen3.8-27B"
    # No rerank model: OVH's smallest text model (Qwen3.5-9B) was measured on the
    # vision stage only, so with RERANKER=llm an OVH scan keeps the fused order.
    # docs/BENCHMARK.md, retrieval: bge-m3 is OVH's best embedding for Arabic queries.
    embedding_model: str = "bge-m3"
    reasoning_effort: ReasoningEffort = "none"
    box_coordinates: BoxCoordinates = BoxCoordinates.THOUSANDTHS
    prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(OVH_PRICES))


class OpenAISettings(ProviderSettings):
    """OpenAI."""

    base_url: str = OPENAI_BASE_URL
    # Measured by docs/BENCHMARK.md (4 October 2026): gpt-5.4-mini without
    # reasoning, pixel boxes, and the free image moderation as the guard.
    vision_model: str = "gpt-5.4-mini-2026-03-17"
    # Decision 46: the chat answers with gpt-5.4-mini, the insight stages' model.
    chat_model: str = "gpt-5.4-mini-2026-03-17"
    # The text stages use the vision stage's model (docs/EVALUATION.md measures them).
    planner_model: str = "gpt-5.4-mini-2026-03-17"
    verify_model: str = "gpt-5.4-mini-2026-03-17"
    compose_model: str = "gpt-5.4-mini-2026-03-17"
    # docs/BENCHMARK.md, retrieval: the best reranker measured (MRR 0.770, about 3 s).
    rerank_model: str = "gpt-5.4-nano-2026-03-17"
    # docs/BENCHMARK.md, retrieval: the best recall and MRR of the three measured,
    # at 1,536 dimensions so pgvector can index it with HNSW.
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: Annotated[int, Field(ge=1, le=2000)] | None = 1536
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


def _check_redis_url(value: str) -> str:
    """Validate a Redis URL: redis(s)://127.0.0.1:6379/<db>, its password kept apart."""
    parts = urlsplit(value.strip())
    if parts.scheme not in REDIS_SCHEMES or not parts.hostname:
        message = "must be a URL of the form redis://127.0.0.1:6379/0"
        raise ValueError(message)
    if parts.hostname == "localhost":
        message = "must name the host 127.0.0.1, not localhost"
        raise ValueError(message)
    if parts.password or parts.username:
        message = "must not carry a user or a password: set REDIS_PASSWORD instead"
        raise ValueError(message)
    database = parts.path.strip("/")
    if database and not database.isdigit():
        message = "must end with a database number, such as /0"
        raise ValueError(message)
    return value.strip()


class _LegacyFeatureKeys(PydanticBaseSettingsSource):
    """
    A settings source that finds the `FEATURE_*` keys of the earlier scheme.

    The environment and the .env files are read with `extra="ignore"` (the root .env also
    carries the web app's keys), so a key the model does not know vanishes. These ones must
    not: production's `FEATURE_SOCIAL=false` would otherwise be dropped and the network
    would switch on.
    """

    def __init__(self, settings_cls: type[BaseSettings], *sources: PydanticBaseSettingsSource):
        super().__init__(settings_cls)
        found: dict[str, str] = {}
        for source in sources:
            variables: Mapping[str, str | None] = getattr(source, "env_vars", {})
            for key, value in variables.items():
                if key.lower().startswith("feature_"):
                    found[key.upper()] = value or ""
        self._found = found

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return {"legacy_feature_keys": self._found} if self._found else {}


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

    # Public addresses. The .test defaults are development-only and are refused
    # in production, which also requires https.
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

    # Admin area (/admin, decision 14), mounted only while the admin feature is on. The
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
    privacy_version: Annotated[str, Field(min_length=1, max_length=32)] = DEFAULT_PRIVACY_VERSION
    # Limits of the support form, shared by every worker through PostgreSQL: per client IP
    # (IPv6 grouped by /48), per reply-to address, and over everyone as a ceiling.
    support_max_per_ip_per_hour: Annotated[int, Field(ge=1)] = 5
    support_max_per_address_per_hour: Annotated[int, Field(ge=1)] = 3
    support_max_per_hour: Annotated[int, Field(ge=1)] = 200
    # Cloudflare Turnstile (decision 56) on sign-up, sign-in, the two mail forms and the support
    # form. Both empty means off; one without the other is refused at start.
    turnstile_site_key: str = ""
    turnstile_secret_key: SecretStr = SecretStr("")
    # Language readiness (decision 36): Arabic only today; every text is keyed by language.
    default_language: str = DEFAULT_LANGUAGE
    supported_languages: Annotated[tuple[str, ...], NoDecode] = (DEFAULT_LANGUAGE,)

    # Feature switches (decision 63): comma-separated names of FeatureFlag. Everything is on
    # unless named in DISABLED_FEATURES, except the OFF_BY_DEFAULT ones, which are on only when
    # named in ENABLED_FEATURES. A child is off while its parent is (PARENT). Read them through
    # `features` and `is_enabled`, never directly.
    disabled_features: str = ""
    enabled_features: str = ""
    # Filled by `_LegacyFeatureKeys` from the environment and the .env files, never by a user:
    # the FEATURE_* keys of the earlier scheme, refused at load because ignoring them would
    # switch a feature that production turned off back on.
    legacy_feature_keys: dict[str, str] = Field(default_factory=dict, exclude=True, repr=False)

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

    # Where consented photos are kept (decisions 8, 19 and 44): "auto" uses the S3 bucket
    # when S3_BUCKET is set and the local disk otherwise; "local" and "s3" force one.
    # Production requires s3. Every S3 key below is required once the resolved backend is s3,
    # and S3 keys without a bucket are refused under auto, so a typo never falls back to disk.
    storage_backend: Literal["auto", "local", "s3"] = "auto"
    # Root of the local store, for development and test; empty is data/media of the checkout.
    local_media_dir: str = ""
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

    # The scripture vectors a new installation imports instead of computing (task 05.4,
    # docs/EMBEDDINGS.md): a local archive or extracted folder, else the archive in the
    # owners' bucket, downloaded once by scripts/vectors/ensure.sh; an empty URL means
    # "never download". Read by the data scripts, kept here so every key is typed.
    vectors_archive: str = ""
    vectors_archive_url: str = (
        "https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz"
    )
    # The scripture store, the world ontology and the learning path (the `corpus` schema,
    # decision 57, docs/CORPUS.md): a local tabsira-corpus-<date>.tar.gz, else the archive
    # in the owners' bucket, downloaded once by scripts/corpus/ensure.sh and checked
    # against its .sha256. An empty URL means "never download": make data then builds
    # the store from the third-party sources and the two corpus files.
    corpus_archive: str = ""
    corpus_archive_url: str = (
        "https://s3-v2.riastorage.com/tabsira/corpus/tabsira-corpus-2026-10-04.tar.gz"
    )
    # GeoNames as one pg_dump of the `geodata` schema (scripts/geodata/ensure.sh): a local
    # file, else this address. Empty by default, so `make data` on a development machine
    # skips the atlas places; the production example names the owners' bucket.
    geodata_dump: str = ""
    geodata_dump_url: str = ""
    # Which of the two the GeoNames step uses; --geonames-source overrides it.
    geonames_source: GeonamesSource = GeonamesSource.DUMP

    # The object detector (services/vision), reached over HTTP only. A detector
    # that does not answer in time is skipped and the scan goes on without boxes.
    detector_url: str = "http://127.0.0.1:8100"
    detector_timeout_seconds: Annotated[float, Field(gt=0)] = 30.0
    # What reranks the evidence candidates (decision 41): the provider's small text
    # model by default. A reranker that fails or does not answer in time is skipped
    # and the fused order is kept.
    # Decision 50: off by default; the verifier judges the fused head itself (docs/EVALUATION.md).
    reranker: RerankerKind = RerankerKind.OFF
    # The cross-encoder of services/vision (POST /rerank), used when RERANKER=cross_encoder;
    # empty switches it off (docs/BENCHMARK.md: about 19 s per 30 passages on a CPU).
    reranker_url: str = "http://127.0.0.1:8100"
    reranker_timeout_seconds: Annotated[float, Field(gt=0)] = 8.0

    # Photos received for a scan: largest upload, and largest decoded size
    # (checked from the header, before decoding: a small file can expand a lot).
    image_max_bytes: Annotated[int, Field(gt=0)] = 15 * 1024 * 1024
    image_max_pixels: Annotated[int, Field(gt=0)] = 40_000_000
    # A photo given by its address is fetched by the server (v2 §6): public
    # addresses and default ports only, within this time and this many redirects.
    image_url_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 12.0
    image_url_max_redirects: Annotated[int, Field(ge=0, le=10)] = 3

    # Redis (decision 21): scan progress for whichever worker holds the reader's
    # stream, and the queue of scan jobs. Durable state stays in PostgreSQL.
    redis_url: str = DEV_REDIS_URL
    # Required in production, where Redis refuses clients without it (decision 22).
    redis_password: SecretStr = SecretStr("")
    # The Redis database the tests use; empty runs them on an in-process fake.
    test_redis_url: str = ""

    # Guests: a signed, httpOnly cookie holds a random key; the server keeps its
    # hash. What a guest saves is kept under it and merged at the first sign-in.
    guest_cookie_name: str = "__Secure-tabsira_guest"
    guest_ttl_days: Annotated[int, Field(ge=1, le=365)] = 90

    # Scans. The engine that proposes insights; `demo` is development-only.
    scan_engine: ScanEngine = ScanEngine.PIPELINE
    # A scan job that runs longer is stopped and reported as failed. Below the
    # queue's ten minutes, after which an unacknowledged job is handed out again.
    scan_job_timeout_seconds: Annotated[float, Field(gt=0, le=540)] = 240.0
    # Seconds the stripped photo stays in the temporary store for its owner.
    scan_image_ttl_seconds: Annotated[int, Field(ge=60, le=86400)] = 3600
    # Seconds the progress events of a scan stay available for a reconnecting reader.
    scan_events_ttl_seconds: Annotated[int, Field(ge=60, le=86400)] = 3600

    # Chat (v2 §14): successful user messages allowed per insight.
    max_chat_user_messages: Annotated[int, Field(ge=0, le=10)] = 3

    # The optional questions (v2 §5): how many of the three the web asks after
    # the first insight, 0 to 3. The web build reads the same key from the root .env.
    profile_questions_max: Annotated[int, Field(ge=0, le=3)] = 3

    # The hidden treasure (v2 §17) shows on return: after this many days, on a
    # visit to its place this many hours after it was hidden, or after a related insight.
    treasure_reveal_after_days: Annotated[int, Field(ge=0, le=365)] = 3
    treasure_return_after_hours: Annotated[int, Field(ge=0, le=720)] = 12

    # Time series (decision 13): days before a chunk is compressed, and dropped.
    scan_events_retention_days: Annotated[int, Field(ge=1, le=3650)] = (
        DEFAULT_SCAN_EVENTS_RETENTION_DAYS
    )
    scan_events_compress_after_days: Annotated[int, Field(ge=1, le=3650)] = (
        DEFAULT_SCAN_EVENTS_COMPRESS_AFTER_DAYS
    )
    ai_calls_retention_days: Annotated[int, Field(ge=1, le=3650)] = DEFAULT_AI_CALLS_RETENTION_DAYS
    ai_calls_compress_after_days: Annotated[int, Field(ge=1, le=3650)] = (
        DEFAULT_AI_CALLS_COMPRESS_AFTER_DAYS
    )
    evidence_exposures_retention_days: Annotated[int, Field(ge=1, le=3650)] = (
        DEFAULT_EXPOSURES_RETENTION_DAYS
    )
    evidence_exposures_compress_after_days: Annotated[int, Field(ge=1, le=3650)] = (
        DEFAULT_EXPOSURES_COMPRESS_AFTER_DAYS
    )

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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Add the source that reports FEATURE_* keys, which `extra="ignore"` would drop."""
        legacy = _LegacyFeatureKeys(settings_cls, env_settings, dotenv_settings)
        return (init_settings, env_settings, dotenv_settings, file_secret_settings, legacy)

    @field_validator("disabled_features")
    @classmethod
    def _check_disabled_features(cls, value: str) -> str:
        parse_flags(value, "DISABLED_FEATURES")
        return value

    @field_validator("enabled_features")
    @classmethod
    def _check_enabled_features(cls, value: str) -> str:
        parse_flags(value, "ENABLED_FEATURES")
        return value

    @model_validator(mode="after")
    def _refuse_legacy_feature_keys(self) -> Self:
        if self.legacy_feature_keys:
            lines = [legacy_advice(key, value) for key, value in self.legacy_feature_keys.items()]
            message = (
                "the FEATURE_* keys are gone and would be ignored, which could switch a feature "
                "back on; use DISABLED_FEATURES and ENABLED_FEATURES instead: " + "; ".join(lines)
            )
            raise ValueError(message)
        return self

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

    @field_validator("session_cookie_name", "guest_cookie_name")
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

    @field_validator("vectors_archive", "corpus_archive", "geodata_dump")
    @classmethod
    def _strip_local_archive(cls, value: str) -> str:
        return value.strip()

    @field_validator("vectors_archive_url", "corpus_archive_url", "geodata_dump_url")
    @classmethod
    def _check_archive_url(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        if value and not value.startswith("https://"):
            key = (info.field_name or "").upper()
            message = f"{key} must be an https address, or empty to never download"
            raise ValueError(message)
        return value

    @field_validator("reranker_url")
    @classmethod
    def _check_reranker_url(cls, value: str) -> str:
        return _origin(value) if value.strip() else ""

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
        if parts.username is not None or parts.password is not None:
            message = "must have no user name or password"
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

    @field_validator("redis_url")
    @classmethod
    def _check_redis_url(cls, value: str) -> str:
        return _check_redis_url(value)

    @field_validator("test_redis_url")
    @classmethod
    def _check_test_redis_url(cls, value: str) -> str:
        return _check_redis_url(value) if value.strip() else ""

    @model_validator(mode="after")
    def _check_redis_and_time_series(self) -> Self:
        """Keep the tests off the development Redis and every compression before its drop."""
        if self.test_redis_url and self.test_redis_url == self.redis_url:
            message = "TEST_REDIS_URL must name another database than REDIS_URL"
            raise ValueError(message)
        for series in ("scan_events", "ai_calls", "evidence_exposures"):
            compress = getattr(self, f"{series}_compress_after_days")
            if compress >= getattr(self, f"{series}_retention_days"):
                message = (
                    f"{series.upper()}_COMPRESS_AFTER_DAYS must be under "
                    f"{series.upper()}_RETENTION_DAYS"
                )
                raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _turnstile_keys_come_together(self) -> Self:
        """Refuse a half-configured Turnstile: the widget and the check need both keys."""
        has_site = bool(self.turnstile_site_key.strip())
        has_secret = bool(self.turnstile_secret_key.get_secret_value().strip())
        if has_site != has_secret:
            missing = "TURNSTILE_SECRET_KEY" if has_site else "TURNSTILE_SITE_KEY"
            message = f"{missing} must be set together with the other Turnstile key"
            raise ValueError(message)
        return self

    @property
    def turnstile_enabled(self) -> bool:
        """Whether the protected forms ask for a Turnstile token."""
        return bool(self.turnstile_secret_key.get_secret_value().strip())

    @field_validator("local_media_dir")
    @classmethod
    def _strip_local_media_dir(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _require_s3_settings(self) -> Self:
        """With the S3 backend every S3 key must be set, so photos are never lost to a typo."""
        if self.resolved_storage_backend != "s3":
            return self._refuse_orphaned_s3_settings()
        missing = [
            name.upper()
            for name in ("s3_bucket", "s3_access_key_id", "s3_public_base_url", "s3_region")
            if not getattr(self, name)
        ]
        if not self.s3_secret_access_key.get_secret_value():
            missing.append("S3_SECRET_ACCESS_KEY")
        if missing:
            subject = (
                "STORAGE_BACKEND=s3"
                if self.storage_backend == "s3"
                else "S3_BUCKET is set, so photos go to S3, which"
            )
            message = f"{subject} needs " + ", ".join(missing)
            raise ValueError(message)
        return self

    def _refuse_orphaned_s3_settings(self) -> Self:
        """`auto` with S3 keys but no bucket is a typo, not a request for the disk."""
        if self.storage_backend != "auto":
            return self
        orphans = [
            name
            for name, value in (
                ("S3_ACCESS_KEY_ID", self.s3_access_key_id),
                ("S3_SECRET_ACCESS_KEY", self.s3_secret_access_key.get_secret_value()),
                ("S3_ENDPOINT_URL", self.s3_endpoint_url),
                ("S3_PUBLIC_BASE_URL", self.s3_public_base_url),
            )
            if value
        ]
        if orphans:
            message = (
                f"{', '.join(orphans)} is set while S3_BUCKET is empty: set the bucket, "
                "or STORAGE_BACKEND=local to keep photos on the development disk"
            )
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
        problems.extend(
            f"{name} must use https in production, not {url}"
            for name, url in (
                [
                    ("SITE_URL", self.site_url),
                    ("API_URL", self.api_url),
                    ("ADMIN_URL", self.admin_url),
                    ("WEB_BASE_URL", self.web_base_url),
                    ("GOOGLE_REDIRECT_URI", self.google_redirect_uri),
                ]
                + [("CORS_ORIGINS", origin) for origin in self.cors_origins]
            )
            if url and urlsplit(url).scheme != "https"
        )
        # Over https the `__Secure-` prefix is a promise browsers enforce; production keeps it.
        problems.extend(
            f"{name} must start with __Secure- in production, not {value}"
            for name, value in (
                ("SESSION_COOKIE_NAME", self.session_cookie_name),
                ("GUEST_COOKIE_NAME", self.guest_cookie_name),
            )
            if not value.startswith("__Secure-")
        )
        problems.extend(self._storage_problems())
        problems.extend(self._turnstile_problems())
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
        if (
            self.is_enabled(FeatureFlag.ADMIN)
            and not self.admin_totp_encryption_key.get_secret_value()
        ):
            problems.append(
                "ADMIN_TOTP_ENCRYPTION_KEY is empty while the admin feature is on "
                "(set a key, or turn the admin area off)"
            )
        if self.google_configured:
            if not self.google_client_secret.get_secret_value():
                problems.append("GOOGLE_CLIENT_ID is set but GOOGLE_CLIENT_SECRET is empty")
            if _host_is_test_domain(self.google_redirect_uri):
                problems.append(
                    f"GOOGLE_REDIRECT_URI points at the development host {self.google_redirect_uri}"
                )
        return problems + self._scan_workflow_problems()

    def _turnstile_problems(self) -> list[str]:
        """Refuse Cloudflare's dummy keys (1x, 2x, 3x) and a site key the web would drop."""
        problems = []
        secret = self.turnstile_secret_key.get_secret_value().strip()
        site = self.turnstile_site_key.strip()
        if site and not TURNSTILE_SITE_KEY_PATTERN.fullmatch(site):
            problems.append("TURNSTILE_SITE_KEY must be 8 to 64 letters, digits, - or _")
        for name, value in (("TURNSTILE_SITE_KEY", site), ("TURNSTILE_SECRET_KEY", secret)):
            if value.startswith(TURNSTILE_TEST_KEY_PREFIXES):
                problems.append(f"{name} is one of Cloudflare's test keys")
        return problems

    def _scan_workflow_problems(self) -> list[str]:
        """List what the scan workflow refuses in production: an open Redis, the simulation."""
        problems = []
        if not self.redis_password.get_secret_value():
            problems.append("REDIS_PASSWORD is empty")
        if self.scan_engine is ScanEngine.DEMO:
            problems.append("SCAN_ENGINE is demo, a development simulation")
        return problems

    def _storage_problems(self) -> list[str]:
        """Production keeps photos in S3 and nowhere else (decision 44)."""
        if self.resolved_storage_backend == "s3":
            return []
        return ["photos must be kept in S3 in production: set STORAGE_BACKEND=s3 and the S3_* keys"]

    @property
    def resolved_storage_backend(self) -> Literal["local", "s3"]:
        """The store in use: `auto` is s3 when S3_BUCKET is set and the local disk otherwise."""
        if self.storage_backend == "auto":
            return "s3" if self.s3_bucket else "local"
        return self.storage_backend

    @property
    def local_media_path(self) -> Path:
        """Root of the local store, resolved; data/media of the checkout when not set."""
        if not self.local_media_dir:
            return checkout_root() / "data" / "media"
        return Path(self.local_media_dir).expanduser().resolve()

    @property
    def features(self) -> frozenset[FeatureFlag]:
        """The features that are on, by the rule of decision 63; computed at each call."""
        return active_flags(
            parse_flags(self.disabled_features, "DISABLED_FEATURES"),
            parse_flags(self.enabled_features, "ENABLED_FEATURES"),
        )

    def is_enabled(self, flag: FeatureFlag) -> bool:
        """Whether `flag` is on."""
        return flag in self.features

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
    def cookie_secure(self) -> bool:
        """
        Whether cookies carry the Secure flag: whenever the web app is served over https.

        Local development runs over plain HTTP on port 80 (decision 49), where a
        browser drops a Secure cookie; production is https and so always Secure.
        """
        return urlsplit(self.site_url).scheme == "https"

    def cookie_name(self, name: str) -> str:
        """
        Return the name a cookie is set and read under.

        A `__Secure-` prefix is a promise browsers enforce: such a cookie is
        refused over plain HTTP, so the prefix is dropped where cookies are not
        Secure, and kept everywhere else.
        """
        return name if self.cookie_secure else name.removeprefix("__Secure-")

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

    @property
    def guest_ttl(self) -> timedelta:
        return timedelta(days=self.guest_ttl_days)

    def redis_connection_url(self, url: str | None = None) -> str:
        """Return `url` (default REDIS_URL) with REDIS_PASSWORD in it, for the client only."""
        chosen = url or self.redis_url
        password = self.redis_password.get_secret_value()
        if not password:
            return chosen
        parts = urlsplit(chosen)
        netloc = f":{quote(password, safe='')}@{parts.netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


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
