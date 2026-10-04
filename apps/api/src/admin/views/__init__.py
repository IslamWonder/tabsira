"""The views the admin area ships with, in the order of its menu."""

from __future__ import annotations

from src.admin.registry import ViewClass
from src.admin.views.accounts import ConsentAdmin, SessionAdmin, UserAdmin
from src.admin.views.learning import (
    LearningDomainAdmin,
    LearningPathVersionAdmin,
    LearningUnitAdmin,
)
from src.admin.views.moderation import (
    ModerationActionAdmin,
    ModerationQueueView,
    ReportAdmin,
)
from src.admin.views.ontology import OntologyCandidateAdmin, OntologyEntityAdmin
from src.admin.views.places import GeoNameAdmin
from src.admin.views.rulings import HadithRulingAdmin, RulingsQueueView
from src.admin.views.security import AdminAuditLogAdmin, TwoFactorView

# sqladmin lists views in the order they are added, so this is the sidebar.
BUILT_IN_VIEWS: tuple[ViewClass, ...] = (
    UserAdmin,
    SessionAdmin,
    ConsentAdmin,
    RulingsQueueView,
    HadithRulingAdmin,
    ModerationQueueView,
    ReportAdmin,
    ModerationActionAdmin,
    OntologyCandidateAdmin,
    OntologyEntityAdmin,
    LearningPathVersionAdmin,
    LearningDomainAdmin,
    LearningUnitAdmin,
    GeoNameAdmin,
    AdminAuditLogAdmin,
    TwoFactorView,
)

__all__ = ["BUILT_IN_VIEWS"]
