"""Import every model here so Alembic and `create_all` see all of them."""

from __future__ import annotations

from src.models.base import Base
from src.models.consent import Consent, ConsentKind
from src.models.email_token import EmailToken, TokenPurpose
from src.models.geo_base import GeoBase
from src.models.geonames import (
    GeoAlternateName,
    GeoCountryInfo,
    GeoHierarchy,
    GeoName,
    GeoPostalCode,
)
from src.models.login_attempt import AttemptKind, LoginAttempt
from src.models.profile import (
    AgeRange,
    Gender,
    Goal,
    KnowledgeLevel,
    Profile,
    ReligiousBackground,
    Theme,
)
from src.models.session import OAuthState, Session
from src.models.user import OAuthAccount, User

__all__ = [
    "AgeRange",
    "AttemptKind",
    "Base",
    "Consent",
    "ConsentKind",
    "EmailToken",
    "Gender",
    "GeoAlternateName",
    "GeoBase",
    "GeoCountryInfo",
    "GeoHierarchy",
    "GeoName",
    "GeoPostalCode",
    "Goal",
    "KnowledgeLevel",
    "LoginAttempt",
    "OAuthAccount",
    "OAuthState",
    "Profile",
    "ReligiousBackground",
    "Session",
    "Theme",
    "TokenPurpose",
    "User",
]
