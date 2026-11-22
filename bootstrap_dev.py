"""
bootstrap_dev.py — One-time local setup for Fiscala development.

Creates PostgreSQL tables and a default admin account.

Run from project root:
    python bootstrap_dev.py

Default login:
    Email:    admin@fiscala.com
    Password: Admin1234!
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone

from app.database import Base, engine, SessionLocal, DATABASE_URL
from app import models
from app.auth.hashing import hash_password


def bootstrap():
    print(f"Database: {DATABASE_URL}")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.email == "admin@fiscala.com").first()
        if existing:
            print("Admin user already exists: admin@fiscala.com")
            return

        user = models.User(
            name="Fiscala Admin",
            email="admin@fiscala.com",
            password=hash_password("Admin1234!"),
        )
        db.add(user)
        db.flush()

        db.add(models.Admin(
            user_id=user.user_id,
            admin_type="super",
            access_scope="full",
            last_login=datetime.now(timezone.utc),
        ))
        db.commit()
        print("Created admin user:")
        print("  Email:    admin@fiscala.com")
        print("  Password: Admin1234!")
    finally:
        db.close()


def main():
    bootstrap()
    try:
        from ensure_role_users import ensure_role_users
        ensure_role_users()
    except Exception as exc:
        print(f"Note: role user setup failed: {exc}")
    try:
        from app.seed_data import seed_data
        seed_data()
    except Exception as exc:
        print(f"Note: sample data seed skipped or failed: {exc}")


if __name__ == "__main__":
    main()
