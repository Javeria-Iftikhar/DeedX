"""
routers/users.py — Routes for Users, Admin, Officer, EconomicAnalyst.

RBAC:
  • User management (create/update/delete) — Admin only
  • List/get users                          — Admin only
  • Role assignments (admin/officer/analyst)— Admin only
  • Self-read (/users/me)                   — Any authenticated user

Audit logging is written after every successful mutating operation.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    get_db,
    require_admin,
)
from app.audit import write_audit_log
from app.crud import users as crud
from app import models, schemas

router = APIRouter(prefix="/users", tags=["Users & Roles"])


# ─── USERS ──────────────────────────────────────────────────────────────────

@router.post("/", response_model=schemas.UserResponse)
def create_user(
    user: schemas.UserCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Create a new user account."""
    obj = crud.create_user(db, user)
    write_audit_log(db, current_user.user_id, f"Created user id={obj.user_id} email={obj.email}", "Users")
    return obj


@router.get("/", response_model=list[schemas.UserResponse])
def list_users(
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** List all users."""
    return crud.get_users(db)


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    """Any authenticated user. Returns the caller's own profile."""
    return current_user


@router.get("/{user_id}", response_model=schemas.UserResponse)
def get_user(
    user_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Retrieve a specific user by ID."""
    obj = crud.get_user(db, user_id)
    if not obj:
        raise HTTPException(404, "User not found")
    return obj


@router.put("/{user_id}", response_model=schemas.UserResponse)
def update_user(
    user_id: int,
    user: schemas.UserUpdate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Update a user's details."""
    obj = crud.update_user(db, user_id, user)
    if not obj:
        raise HTTPException(404, "User not found")
    write_audit_log(db, current_user.user_id, f"Updated user id={user_id}", "Users")
    return obj


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Delete a user account."""
    if user_id == current_user.user_id:
        raise HTTPException(400, "You cannot delete your own account")
    obj = crud.delete_user(db, user_id)
    if not obj:
        raise HTTPException(404, "User not found")
    write_audit_log(db, current_user.user_id, f"Deleted user id={user_id}", "Users")
    return {"msg": "deleted"}


# ─── ADMIN ──────────────────────────────────────────────────────────────────

@router.post("/admin/", response_model=schemas.AdminResponse, tags=["Admin Role"])
def create_admin(
    data: schemas.AdminCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Assign the Admin role to a user."""
    obj = crud.create_admin(db, data)
    write_audit_log(db, current_user.user_id, f"Assigned Admin role to user_id={data.user_id}", "Admin")
    return obj


@router.get("/admin/", response_model=list[schemas.AdminResponse], tags=["Admin Role"])
def list_admins(
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** List all admin role assignments."""
    return crud.get_admins(db)


@router.get("/admin/{user_id}", response_model=schemas.AdminResponse, tags=["Admin Role"])
def get_admin(
    user_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Retrieve a specific admin record."""
    obj = crud.get_admin(db, user_id)
    if not obj:
        raise HTTPException(404, "Admin not found")
    return obj


@router.delete("/admin/{user_id}", tags=["Admin Role"])
def delete_admin(
    user_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Remove Admin role from a user."""
    if user_id == current_user.user_id:
        raise HTTPException(400, "You cannot remove your own Admin role")
    obj = crud.delete_admin(db, user_id)
    if not obj:
        raise HTTPException(404, "Admin not found")
    write_audit_log(db, current_user.user_id, f"Removed Admin role from user_id={user_id}", "Admin")
    return {"msg": "deleted"}


# ─── OFFICER ────────────────────────────────────────────────────────────────

@router.post("/officer/", response_model=schemas.OfficerResponse, tags=["Officer Role"])
def create_officer(
    data: schemas.OfficerCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Assign the Officer role to a user."""
    obj = crud.create_officer(db, data)
    write_audit_log(db, current_user.user_id, f"Assigned Officer role to user_id={data.user_id}", "Officer")
    return obj


@router.get("/officer/", response_model=list[schemas.OfficerResponse], tags=["Officer Role"])
def list_officers(
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** List all officer role assignments."""
    return crud.get_officers(db)


@router.get("/officer/{user_id}", response_model=schemas.OfficerResponse, tags=["Officer Role"])
def get_officer(
    user_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Retrieve a specific officer record."""
    obj = crud.get_officer(db, user_id)
    if not obj:
        raise HTTPException(404, "Officer not found")
    return obj


@router.delete("/officer/{user_id}", tags=["Officer Role"])
def delete_officer(
    user_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Remove Officer role from a user."""
    obj = crud.delete_officer(db, user_id)
    if not obj:
        raise HTTPException(404, "Officer not found")
    write_audit_log(db, current_user.user_id, f"Removed Officer role from user_id={user_id}", "Officer")
    return {"msg": "deleted"}


# ─── ECONOMIC ANALYST ───────────────────────────────────────────────────────

@router.post("/analyst/", response_model=schemas.EconomicAnalystResponse, tags=["Analyst Role"])
def create_analyst(
    data: schemas.EconomicAnalystCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Assign the Economic Analyst role to a user."""
    obj = crud.create_analyst(db, data)
    write_audit_log(db, current_user.user_id, f"Assigned EconomicAnalyst role to user_id={data.user_id}", "EconomicAnalyst")
    return obj


@router.get("/analyst/", response_model=list[schemas.EconomicAnalystResponse], tags=["Analyst Role"])
def list_analysts(
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** List all economic analyst role assignments."""
    return crud.get_analysts(db)


@router.get("/analyst/{user_id}", response_model=schemas.EconomicAnalystResponse, tags=["Analyst Role"])
def get_analyst(
    user_id: int,
    _admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Retrieve a specific analyst record."""
    obj = crud.get_analyst(db, user_id)
    if not obj:
        raise HTTPException(404, "Analyst not found")
    return obj


@router.delete("/analyst/{user_id}", tags=["Analyst Role"])
def delete_analyst(
    user_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """**Admin only.** Remove Economic Analyst role from a user."""
    obj = crud.delete_analyst(db, user_id)
    if not obj:
        raise HTTPException(404, "Analyst not found")
    write_audit_log(db, current_user.user_id, f"Removed EconomicAnalyst role from user_id={user_id}", "EconomicAnalyst")
    return {"msg": "deleted"}
