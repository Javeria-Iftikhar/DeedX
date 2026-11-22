"""
database.py — SQLAlchemy engine, session, and Base.

Connects to PostgreSQL only (imf_db).
Set DATABASE_URL in app/.env to match your local PostgreSQL password.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

try:
    from dotenv import load_dotenv
    # override=True so app/.env wins over stale machine/user GROQ_API_KEY variables
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:123@127.0.0.1:5432/imf_db",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()
