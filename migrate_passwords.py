"""
migrate_passwords.py — One-time script to hash any plain-text passwords
already present in the Users table.

Run ONCE before deploying the auth-extended backend:

    cd imf_backend_extended
    python migrate_passwords.py

It detects passwords that are NOT already bcrypt hashes (bcrypt hashes
start with '$2b$') and replaces them with hashed versions.
"""

import sys
import os

# Make app importable
sys.path.insert(0, os.path.dirname(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join("app", ".env"))
except ImportError:
    pass

from app.database import SessionLocal
from app import models
from app.auth.hashing import hash_password

def migrate():
    db = SessionLocal()
    try:
        users = db.query(models.User).all()
        migrated = 0
        for user in users:
            pwd = user.password or ""
            if not pwd.startswith("$2b$") and not pwd.startswith("$2a$"):
                user.password = hash_password(pwd)
                migrated += 1
                print(f"  Hashed password for user_id={user.user_id} ({user.email})")
        db.commit()
        print(f"\nDone. {migrated} password(s) migrated out of {len(users)} users.")
    finally:
        db.close()

if __name__ == "__main__":
    print("Migrating plain-text passwords to bcrypt hashes...\n")
    migrate()
