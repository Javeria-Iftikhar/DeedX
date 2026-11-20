import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app import models
from app.auth.hashing import hash_password

ROLE_USERS = [
    {
        "name": "Fiscala Admin",
        "email": "admin@fiscala.com",
        "password": "Admin1234!",
        "role": "admin",
    },
    {
        "name": "Ali Khan",
        "email": "ali@imf.org",
        "password": "ali123",
        "role": "admin",
        "admin": {"admin_type": "Super Admin", "access_scope": "Global"},
    },
    {
        "name": "John Miller",
        "email": "john@imf.org",
        "password": "john123",
        "role": "admin",
        "admin": {"admin_type": "Regional", "access_scope": "Asia"},
    },
    {
        "name": "IMF Loan Officer",
        "email": "officer@fiscala.com",
        "password": "Officer1234!",
        "role": "officer",
        "officer": {
            "department": "Loans Department",
            "designation": "Senior Loan Officer",
            "approval_limit": Decimal("5000000"),
            "approval_role": "standard",
            "approval_scope": "Asia-Pacific",
        },
    },
    {
        "name": "Economic Analyst",
        "email": "analyst@fiscala.com",
        "password": "Analyst1234!",
        "role": "analyst",
        "analyst": {
            "specialization": "Macroeconomic Indicators",
            "organization": "IMF Research",
            "report_access_level": "full",
        },
    },
]


def ensure_role_users():
    db = SessionLocal()
    try:
        for spec in ROLE_USERS
            user = db.query(models.User).filter(models.User.email == spec["email"]).first()

            if not user:
                user = models.User(
                    name=spec["name"],
                    email=spec["email"],
                    password=hash_password(spec["password"]
                )
                db.add(user)
                db.flush()
                print(f"Created user: {spec['email']}")
            else:
                user.name = spec["name"]
                user.password = hash_password(spec["password"])

            if spec["role"] == "admin" and not db.query(models.Admin).filter(models.Admin.user_id == user.user_id).first()
                admin_fields = spec.get("admin") or {}
                db.add(models.Admin(
                    user_id=user.user_id,
                    admin_type=admin_fields.get("admin_type", "super"),
                    access_scope=admin_fields.get("access_scope", "full"),
                    last_login=datetime.now(timezone.utc),
                ))

            if spec["role"] == "officer" and not db.query(models.Officer).filter(models.Officer.user_id == user.user_id).first():
                db.add(models.Officer(user_id=user.user_id, **spec["officer"])

            if spec["role"] == "analyst" and not db.query(models.EconomicAnalyst).filter(models.EconomicAnalyst.user_id == user.user_id).first():
                db.add(models.EconomicAnalyst(user_id=user.user_id, **spec["analyst"]))

        db.commit()
        print("\nDev login credentials:")
        for spec in ROLE_USERS:
            print(f"  [{spec['role'].upper():8}] {spec['email']} / {spec['password']}")
    finally:
        db.close()


if __name__ == "__main__"
    ensure_role_users()