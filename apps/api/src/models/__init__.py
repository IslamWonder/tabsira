"""Import every model here so Alembic and `create_all` see all of them."""

from __future__ import annotations

from src.models.admin_access import AdminSession, AdminTotp
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
from src.models.moderation import (
    ModerationAction,
    ModerationActionKind,
    ModerationSource,
    ModerationTarget,
)
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
from src.models.public_id import public_id_pk
from src.models.retrieval import (
    EmbeddedCorpus,
    EmbeddingRun,
    EmbeddingRunStatus,
    HadithEmbedding,
    QuranVerseEmbedding,
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
from src.models.social import (
    Block,
    Bookmark,
    Comment,
    CommentStatus,
    Follow,
    InsightPublication,
    Post,
    PostLike,
    PostStatus,
    PostVisibility,
    RemovalSource,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
)
from src.models.user import OAuthAccount, User

__all__ = [
    "AdminAuditLog",
    "AdminSession",
    "AdminTotp",
    "AgeRange",
    "AttemptKind",
    "AuditAction",
    "Base",
    "Block",
    "Bookmark",
    "CandidateKind",
    "CandidateStatus",
    "Comment",
    "CommentStatus",
    "Consent",
    "ConsentKind",
    "CookieConsent",
    "EmailToken",
    "EmbeddedCorpus",
    "EmbeddingRun",
    "EmbeddingRunStatus",
    "Follow",
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
    "HadithEmbedding",
    "HadithRuling",
    "HadithSearch",
    "HadithSignal",
    "HadithVerificationQueue",
    "InsightPublication",
    "KnowledgeLevel",
    "LearnerUnitState",
    "LearningDomain",
    "LearningPathVersion",
    "LearningUnit",
    "LoginAttempt",
    "ModerationAction",
    "ModerationActionKind",
    "ModerationSource",
    "ModerationTarget",
    "OAuthAccount",
    "OAuthState",
    "OntologyCandidate",
    "OntologyEntity",
    "Post",
    "PostLike",
    "PostStatus",
    "PostVisibility",
    "Profile",
    "QuranAnnotation",
    "QuranSurah",
    "QuranVerse",
    "QuranVerseEmbedding",
    "QuranVerseHistory",
    "QuranVerseSearch",
    "ReligiousBackground",
    "RemovalSource",
    "Report",
    "ReportReason",
    "ReportStatus",
    "ReportTarget",
    "ScriptureAudit",
    "ScriptureSyncState",
    "Session",
    "Theme",
    "TokenPurpose",
    "User",
    "public_id_pk",
]
