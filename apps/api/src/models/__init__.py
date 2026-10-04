"""Import every model here so Alembic and `create_all` see all of them."""

from __future__ import annotations

from src.models.admin_audit import AdminAuditLog, AuditAction
from src.models.base import Base
from src.models.consent import Consent, ConsentKind
from src.models.cookie_consent import CookieConsent
from src.models.email_token import EmailToken, TokenPurpose
from src.models.geo_base import GeoBase
from src.models.geonames import (
    GeoAlternateName,
    GeoCountryInfo,
    GeoHierarchy,
    GeoName,
    GeoPostalCode,
)
from src.models.learning import (
    LearnerUnitState,
    LearningDomain,
    LearningPathVersion,
    LearningUnit,
)
from src.models.login_attempt import AttemptKind, LoginAttempt
from src.models.ontology import CandidateKind, CandidateStatus, OntologyCandidate, OntologyEntity
from src.models.profile import (
    AgeRange,
    Gender,
    Goal,
    KnowledgeLevel,
    Profile,
    ReligiousBackground,
    Theme,
)
from src.models.scripture import (
    Hadith,
    HadithClassification,
    HadithCollection,
    HadithRuling,
    HadithSearch,
    HadithSignal,
    HadithVerificationQueue,
    QuranAnnotation,
    QuranSurah,
    QuranVerse,
    QuranVerseHistory,
    QuranVerseSearch,
    ScriptureAudit,
    ScriptureSyncState,
)
from src.models.session import OAuthState, Session
from src.models.user import OAuthAccount, User

__all__ = [
    "AdminAuditLog",
    "AgeRange",
    "AttemptKind",
    "AuditAction",
    "Base",
    "CandidateKind",
    "CandidateStatus",
    "Consent",
    "ConsentKind",
    "CookieConsent",
    "EmailToken",
    "Gender",
    "GeoAlternateName",
    "GeoBase",
    "GeoCountryInfo",
    "GeoHierarchy",
    "GeoName",
    "GeoPostalCode",
    "Goal",
    "Hadith",
    "HadithClassification",
    "HadithCollection",
    "HadithRuling",
    "HadithSearch",
    "HadithSignal",
    "HadithVerificationQueue",
    "KnowledgeLevel",
    "LearnerUnitState",
    "LearningDomain",
    "LearningPathVersion",
    "LearningUnit",
    "LoginAttempt",
    "OAuthAccount",
    "OAuthState",
    "OntologyCandidate",
    "OntologyEntity",
    "Profile",
    "QuranAnnotation",
    "QuranSurah",
    "QuranVerse",
    "QuranVerseHistory",
    "QuranVerseSearch",
    "ReligiousBackground",
    "ScriptureAudit",
    "ScriptureSyncState",
    "Session",
    "Theme",
    "TokenPurpose",
    "User",
]
