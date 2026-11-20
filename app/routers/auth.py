"""
routers/auth.py — Authentication endpoints.

POST /auth/register  — self-register as officer or economic_analyst
POST /auth/login     — returns access + refresh tokens
POST /auth/refresh   — exchange refresh token for new access token
POST /auth/logout    — client-side; server logs the event
GET  /auth/me        — return current user profile + role
POST /auth/change-password — authenticated user changes their own password

All endpoints write audit log entries on meaningful events.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.audit import write_audit_log
from app.auth.dependencies import (
    create_access_token,
    create_refresh_token,
    decode_token,
    detect_role,
    get_current_user,
    get_db,
)
from app.auth.hashing import hash_password, verify_password
from app import models, schemas

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Pydantic schemas (auth-specific) ─────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    user_type: str

    @field_validator("user_type")
    @classmethod
    def validate_user_type(cls, v):
        allowed_roles = ["officer", "economic_analyst"]
        if v not in allowed_roles:
            raise ValueError("user_type must be either 'officer' or 'economic_analyst'")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        import re
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Invalid email address format")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    user_id: int
    name: str
    email: str
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError("New password must be at least 8 characters long")
        return v


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=schemas.UserResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new officer or economic_analyst.
    Admins cannot self-register — admin accounts must be created by an existing admin.
    Password is hashed with bcrypt before storage.
    """
    existing = db.query(models.User).filter(models.User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = hash_password(body.password)
    user = models.User(name=body.name, email=body.email, password=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)

    if body.user_type == "officer":
        subtype = models.Officer(
            user_id=user.user_id,
            department="Unassigned",
            designation="Officer",
            approval_limit=0,
            approval_role="standard",
            approval_scope="none",
        )
    else:  # economic_analyst
        subtype = models.EconomicAnalyst(
            user_id=user.user_id,
            specialization="General",
            organization="IMF",
            report_access_level="basic",
        )

    db.add(subtype)
    db.commit()

    write_audit_log(db, user.user_id, f"User registered as {body.user_type}", "Users")
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate with email + password.
    Returns JWT access token (60 min) and refresh token (7 days).
    """
    user = db.query(models.User).filter(models.User.email == body.email).first()

    if not user or not verify_password(body.password, user.password):
        if user:
            write_audit_log(db, user.user_id, "Login failed — wrong password", "Users")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    role = detect_role(db, user.user_id)
    if not role:
        raise HTTPException(status_code=403, detail="User has no assigned role in the system")

    # Update Admin.last_login if applicable
    admin_row = db.query(models.Admin).filter(models.Admin.user_id == user.user_id).first()
    if admin_row:
        admin_row.last_login = datetime.now(timezone.utc)
        db.commit()

    write_audit_log(db, user.user_id, "Login successful", "Users")

    return TokenResponse(
        access_token=create_access_token(user.user_id, role),
        refresh_token=create_refresh_token(user.user_id, role),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access token + refresh token."""
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type — expected refresh token")

    user_id = int(payload["sub"])
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    role = detect_role(db, user_id)
    if not role:
        raise HTTPException(status_code=403, detail="User has no role")

    write_audit_log(db, user_id, "Token refreshed", "Users")

    return TokenResponse(
        access_token=create_access_token(user_id, role),
        refresh_token=create_refresh_token(user_id, role),
    )


@router.post("/logout")
def logout(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Stateless logout — client must discard the token.
    Server logs the event for audit purposes.
    """
    write_audit_log(db, current_user.user_id, "Logout", "Users")
    return {"message": "Logged out successfully. Please discard your token."}


@router.get("/me", response_model=MeResponse)
def me(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return current user's profile and detected role."""
    role = detect_role(db, current_user.user_id) or "unknown"
    return MeResponse(
        user_id=current_user.user_id,
        name=current_user.name,
        email=current_user.email,
        role=role,
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Authenticated users can change their own password.
    Requires supplying the current password for verification.
    """
    if not verify_password(body.current_password, current_user.password):
        write_audit_log(db, current_user.user_id, "Password change failed — wrong current password", "Users")
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password = hash_password(body.new_password)
    db.commit()

    write_audit_log(db, current_user.user_id, "Password changed successfully", "Users")
    return {"message": "Password changed successfully"}
