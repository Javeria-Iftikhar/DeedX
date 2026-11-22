"""
crud/users.py — CRUD for Users, Admin, Officer, EconomicAnalyst, AuditLog

Passwords are hashed with bcrypt before storage.
AuditLog creation uses write_audit_log() from app.audit for proper log_id sequencing.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session
from app import models, schemas
from app.auth.hashing import hash_password
from datetime import datetime, timezone


# ─── USER ───────────────────────────────────────────────────────────────────

def create_user(db: Session, user: schemas.UserCreate):
    from fastapi import HTTPException
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user.password)
    obj = models.User(name=user.name, email=user.email, password=hashed)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def get_users(db: Session):
    return db.query(models.User).all()

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.user_id == user_id).first()

def update_user(db: Session, user_id: int, user: schemas.UserUpdate):
    obj = get_user(db, user_id)
    if not obj:
        return None
    if user.name is not None:
        obj.name = user.name
    if user.email is not None:
        obj.email = user.email
    if user.password is not None:
        obj.password = hash_password(user.password)
    db.commit(); db.refresh(obj)
    return obj

def delete_user(db: Session, user_id: int):
    obj = get_user(db, user_id)
    if not obj:
        return None
    db.delete(obj); db.commit()
    return obj


# ─── ADMIN ──────────────────────────────────────────────────────────────────

def create_admin(db: Session, data: schemas.AdminCreate):
    from fastapi import HTTPException
    if not get_user(db, data.user_id):
        raise HTTPException(status_code=404, detail=f"User {data.user_id} not found")
    if get_admin(db, data.user_id):
        raise HTTPException(status_code=400, detail="User already has Admin role")
    obj = models.Admin(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def get_admins(db: Session):
    return db.query(models.Admin).all()

def get_admin(db: Session, user_id: int):
    return db.query(models.Admin).filter(models.Admin.user_id == user_id).first()

def delete_admin(db: Session, user_id: int):
    obj = get_admin(db, user_id)
    if not obj:
        return None
    db.delete(obj); db.commit()
    return obj


# ─── OFFICER ────────────────────────────────────────────────────────────────

def create_officer(db: Session, data: schemas.OfficerCreate):
    from fastapi import HTTPException
    if not get_user(db, data.user_id):
        raise HTTPException(status_code=404, detail=f"User {data.user_id} not found")
    if get_officer(db, data.user_id):
        raise HTTPException(status_code=400, detail="User already has Officer role")
    obj = models.Officer(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def get_officers(db: Session):
    return db.query(models.Officer).all()

def get_officer(db: Session, user_id: int):
    return db.query(models.Officer).filter(models.Officer.user_id == user_id).first()

def delete_officer(db: Session, user_id: int):
    obj = get_officer(db, user_id)
    if not obj:
        return None
    db.delete(obj); db.commit()
    return obj


# ─── ECONOMIC ANALYST ───────────────────────────────────────────────────────

def create_analyst(db: Session, data: schemas.EconomicAnalystCreate):
    from fastapi import HTTPException
    if not get_user(db, data.user_id):
        raise HTTPException(status_code=404, detail=f"User {data.user_id} not found")
    if get_analyst(db, data.user_id):
        raise HTTPException(status_code=400, detail="User already has EconomicAnalyst role")
    obj = models.EconomicAnalyst(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def get_analysts(db: Session):
    return db.query(models.EconomicAnalyst).all()

def get_analyst(db: Session, user_id: int):
    return db.query(models.EconomicAnalyst).filter(models.EconomicAnalyst.user_id == user_id).first()

def delete_analyst(db: Session, user_id: int):
    obj = get_analyst(db, user_id)
    if not obj:
        return None
    db.delete(obj); db.commit()
    return obj


# ─── AUDIT LOG ──────────────────────────────────────────────────────────────
# Note: prefer using app.audit.write_audit_log() directly in routers.
# These functions remain for backward-compatibility with any internal callers.

def create_audit_log(db: Session, data: schemas.AuditLogCreate):
    max_id = db.query(func.max(models.AuditLog.log_id)).scalar() or 0
    obj = models.AuditLog(
        user_id=data.user_id,
        log_id=max_id + 1,
        action=data.action,
        log_timestamp=datetime.now(timezone.utc),
        entity_affected=data.entity_affected,
    )
    db.add(obj); db.commit()
    return obj

def get_audit_logs(db: Session):
    return db.query(models.AuditLog).order_by(models.AuditLog.log_timestamp.desc()).all()

def get_audit_logs_by_user(db: Session, user_id: int):
    return (
        db.query(models.AuditLog)
        .filter(models.AuditLog.user_id == user_id)
        .order_by(models.AuditLog.log_timestamp.desc())
        .all()
    )
