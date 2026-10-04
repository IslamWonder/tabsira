"""The admin landing page: counts, never records."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src import clock
from src.models.admin_access import AdminSession
from src.models.admin_audit import AdminAuditLog, AuditAction
from src.models.consent import Consent
from src.models.learning import LearningDomain, LearningPathVersion, LearningUnit
from src.models.ontology import CandidateStatus, OntologyCandidate, OntologyEntity
from src.models.session import Session
from src.models.user import User
from src.services import admin_totp_service

# The audit counts cover this long; the retention keeps far more, but a dashboard
# answers "what happened lately".
RECENT = timedelta(hours=24)


async def _count(db: AsyncSession, table: Any, *where: ColumnElement[bool]) -> int:
    """Count the rows of `table` that match every condition."""
    total = await db.scalar(select(func.count()).select_from(table).where(*where))
    return total or 0


async def estimated_geonames(db: AsyncSession) -> int:
    """
    Return roughly how many places GeoNames holds, without counting them.

    The table holds millions of rows and an exact count reads them all, on every page
    load. The planner's own estimate is a catalogue lookup; it is negative until the
    table has been analysed, and then the answer is zero rather than a guess.
    """
    estimate = await db.scalar(
        text("SELECT reltuples::bigint FROM pg_class WHERE oid = 'geodata.geonames'::regclass")
    )
    return max(estimate or 0, 0)


async def collect(db: AsyncSession, admin_id: uuid.UUID) -> dict[str, Any]:
    """Gather the dashboard's numbers for the admin who is looking at it."""
    now = clock.utcnow()
    since = now - RECENT
    audit_recent = AdminAuditLog.at >= since
    active_version = await db.scalar(
        select(LearningPathVersion).where(LearningPathVersion.is_active.is_(True))
    )
    return {
        "users": await _count(db, User, User.deleted_at.is_(None)),
        "active_users": await _count(db, User, User.deleted_at.is_(None), User.is_active.is_(True)),
        "admins": await _count(db, User, User.is_admin.is_(True), User.deleted_at.is_(None)),
        "user_sessions": await _count(db, Session, Session.expires_at > now),
        "admin_sessions": await _count(db, AdminSession, AdminSession.expires_at > now),
        "consents": await _count(db, Consent),
        "candidates_new": await _count(
            db, OntologyCandidate, OntologyCandidate.status == CandidateStatus.NEW
        ),
        "candidates_accepted": await _count(
            db, OntologyCandidate, OntologyCandidate.status == CandidateStatus.ACCEPTED
        ),
        "candidates_rejected": await _count(
            db, OntologyCandidate, OntologyCandidate.status == CandidateStatus.REJECTED
        ),
        "entities": await _count(db, OntologyEntity),
        "path_versions": await _count(db, LearningPathVersion),
        "active_version": active_version,
        "active_domains": 0
        if active_version is None
        else await _count(
            db, LearningDomain, LearningDomain.path_version == active_version.path_version
        ),
        "active_units": 0
        if active_version is None
        else await _count(
            db, LearningUnit, LearningUnit.path_version == active_version.path_version
        ),
        "places": await estimated_geonames(db),
        "audit_events": await _count(db, AdminAuditLog, audit_recent),
        "sign_ins": await _count(
            db, AdminAuditLog, audit_recent, AdminAuditLog.action == AuditAction.SIGN_IN
        ),
        "failed_sign_ins": await _count(
            db, AdminAuditLog, audit_recent, AdminAuditLog.action == AuditAction.SIGN_IN_FAILED
        ),
        "two_factor": admin_totp_service.is_enabled(await admin_totp_service.get(db, admin_id)),
    }
