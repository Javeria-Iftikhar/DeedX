"""
routers/audit_logs.py — Audit Log read endpoints with RBAC.

GET /audit-logs/                      — Admin only: all logs with optional filters
GET /audit-logs/my                    — Any authenticated user: their own logs
GET /audit-logs/user/{user_id}        — Admin only: logs for a specific user
GET /audit-logs/{log_id}              — Admin only: single log entry

Audit logs are APPEND-ONLY:
  • No POST, PUT, PATCH, or DELETE routes are exposed here.
  • Records are created exclusively via app.audit.write_audit_log().

Filter parameters (all optional, admin-only list endpoint):
  • user_id       — filter by user
  • action        — case-insensitive substring match
  • entity        — case-insensitive substring match
  • date_from     — inclusive lower bound (YYYY-MM-DD)
  • date_to       — inclusive upper bound (YYYY-MM-DD)
"""

from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_db, require_admin
from app import models, schemas

router = APIRouter(prefix="/audit-logs", tags=["Audit Log"])


# ── Admin: full log access with filtering ─────────────────────────────────────

@router.get("/", response_model=List[schemas.AuditLogResponse])
def list_all_audit_logs(
    user_id:   Optional[int]  = Query(None, description="Filter by user_id"),
    action:    Optional[str]  = Query(None, description="Substring match on action text"),
    entity:    Optional[str]  = Query(None, description="Substring match on entity_affected"),
    date_from: Optional[date] = Query(None, description="Lower bound on log_timestamp (inclusive)"),
    date_to:   Optional[date] = Query(None, description="Upper bound on log_timestamp (inclusive)"),
    _admin:    models.User    = Depends(require_admin),
    db:        Session        = Depends(get_db),
) -> List[models.AuditLog]:
    """
    **Admin only.** Returns all audit log entries with optional filters.
    Audit records are read-only and can never be modified or deleted.
    """
    q = db.query(models.AuditLog)

    if user_id is not None:
        q = q.filter(models.AuditLog.user_id == user_id)

    if action:
        q = q.filter(models.AuditLog.action.ilike(f"%{action}%"))

    if entity:
        q = q.filter(models.AuditLog.entity_affected.ilike(f"%{entity}%"))

    if date_from:
        dt_from = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=timezone.utc)
        q = q.filter(models.AuditLog.log_timestamp >= dt_from)

    if date_to:
        dt_to = datetime.combine(date_to, datetime.max.time()).replace(tzinfo=timezone.utc)
        q = q.filter(models.AuditLog.log_timestamp <= dt_to)

    return q.order_by(models.AuditLog.log_timestamp.desc()).all()


# ── Any authenticated user: own logs ─────────────────────────────────────────

@router.get("/my", response_model=List[schemas.AuditLogResponse])
def my_audit_logs(
    action:    Optional[str]  = Query(None, description="Substring match on action text"),
    entity:    Optional[str]  = Query(None, description="Substring match on entity_affected"),
    date_from: Optional[date] = Query(None, description="Lower bound on log_timestamp (inclusive)"),
    date_to:   Optional[date] = Query(None, description="Upper bound on log_timestamp (inclusive)"),
    current_user: models.User = Depends(get_current_user),
    db: Session               = Depends(get_db),
) -> List[models.AuditLog]:
    """
    Returns audit log entries for the currently authenticated user.
    Available to all authenticated users.
    """
    q = db.query(models.AuditLog).filter(
        models.AuditLog.user_id == current_user.user_id
    )

    if action:
        q = q.filter(models.AuditLog.action.ilike(f"%{action}%"))

    if entity:
        q = q.filter(models.AuditLog.entity_affected.ilike(f"%{entity}%"))

    if date_from:
        dt_from = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=timezone.utc)
        q = q.filter(models.AuditLog.log_timestamp >= dt_from)

    if date_to:
        dt_to = datetime.combine(date_to, datetime.max.time()).replace(tzinfo=timezone.utc)
        q = q.filter(models.AuditLog.log_timestamp <= dt_to)

    return q.order_by(models.AuditLog.log_timestamp.desc()).all()


# ── Admin: logs for a specific user ──────────────────────────────────────────

@router.get("/user/{user_id}", response_model=List[schemas.AuditLogResponse])
def user_audit_logs(
    user_id: int,
    _admin:  models.User = Depends(require_admin),
    db:      Session     = Depends(get_db),
) -> List[models.AuditLog]:
    """**Admin only.** Returns all audit log entries for a specific user."""
    return (
        db.query(models.AuditLog)
        .filter(models.AuditLog.user_id == user_id)
        .order_by(models.AuditLog.log_timestamp.desc())
        .all()
    )


# ── Admin: single log entry ───────────────────────────────────────────────────

@router.get("/{log_id}", response_model=schemas.AuditLogResponse)
def get_audit_log(
    log_id:  int,
    _admin:  models.User = Depends(require_admin),
    db:      Session     = Depends(get_db),
) -> models.AuditLog:
    """**Admin only.** Returns a single audit log entry by log_id."""
    obj = db.query(models.AuditLog).filter(models.AuditLog.log_id == log_id).first()
    if not obj:
        raise HTTPException(404, "Audit log entry not found")
    return obj
