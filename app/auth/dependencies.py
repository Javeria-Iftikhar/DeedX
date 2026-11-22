"""
auth/dependencies.py — JWT creation/verification + FastAPI dependency functions.

Reads JWT settings from environment variables (loaded from app/.env).

Role detection uses ISA subtype tables only (no role column in Users):
  Admin table        → role = "admin"
  Officer table      → role = "officer"
  EconomicAnalyst    → role = "analyst"
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

# Ensure .env is loaded before reading env vars
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)
except ImportError:
    pass

from app.database import SessionLocal
from app import models

# ── Config ────────────────────────────────────────────────────────────────────

SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "changeme-use-a-real-secret-in-production")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

oauth2_scheme = HTTPBearer()

# ── DB dependency ─────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Role detection ────────────────────────────────────────────────────────────

def detect_role(db: Session, user_id: int) -> Optional[str]:
    if db.query(models.Admin).filter(models.Admin.user_id == user_id).first():
        return "admin"
    if db.query(models.Officer).filter(models.Officer.user_id == user_id).first():
        return "officer"
    if db.query(models.EconomicAnalyst).filter(models.EconomicAnalyst.user_id == user_id).first():
        return "analyst"
    return None


# ── Token utilities ───────────────────────────────────────────────────────────

def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "refresh",
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _get_token(credentials: HTTPAuthorizationCredentials) -> str:
    return credentials.credentials


# ── Current user ──────────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:

    token = _get_token(credentials)
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = int(payload["sub"])
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# ── Role dependencies ─────────────────────────────────────────────────────────

def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:

    token = _get_token(credentials)
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    user_id = int(payload["sub"])
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_officer(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:

    token = _get_token(credentials)
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    role = payload.get("role")
    if role not in ("admin", "officer"):
        raise HTTPException(status_code=403, detail="Officer or Admin access required")

    user_id = int(payload["sub"])
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_staff(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    """Admin, officer, or analyst — for shared read-only reference data (e.g. countries)."""
    token = _get_token(credentials)
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    role = payload.get("role")
    if role not in ("admin", "officer", "analyst"):
        raise HTTPException(status_code=403, detail="Staff access required")

    user_id = int(payload["sub"])
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_analyst(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:

    token = _get_token(credentials)
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    role = payload.get("role")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Analyst or Admin access required")

    user_id = int(payload["sub"])
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
