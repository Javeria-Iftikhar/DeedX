"""Reset known login passwords and ensure admin/officer/analyst role rows exist."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from dotenv import load_dotenv
load_dotenv(root / "app" / ".env")

from app.database import SessionLocal
from app import models
from app.auth.hashing import hash_password, verify_password
from app.auth.dependencies import detect_role

# email -> (plain_password, role)
ACCOUNTS = {
    "ali@imf.org": ("ali123", "admin"),
    "john@imf.org": ("john123", "admin"),
    "sara@imf.org": ("sara123", "officer"),
    "carlos@imf.org": ("carlos123", "officer"),
    "fatima@imf.org": ("fatima123", "analyst"),
}

db = SessionLocal()
try:
    for email, (plain, role) in ACCOUNTS.items():
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            print(f"SKIP missing user: {email}")
            continue

        user.password = hash_password(plain)
        uid = user.user_id

        if role == "admin":
            if not db.query(models.Admin).filter(models.Admin.user_id == uid).first():
                db.add(models.Admin(user_id=uid, admin_type="Admin", access_scope="Global"))
        elif role == "officer":
            if not db.query(models.Officer).filter(models.Officer.user_id == uid).first():
                db.add(
                    models.Officer(
                        user_id=uid,
                        department="Loans",
                        designation="Loan Officer",
                        approval_limit=0,
                    )
                )
        elif role == "analyst":
            if not db.query(models.EconomicAnalyst).filter(models.EconomicAnalyst.user_id == uid).first():
                db.add(
                    models.EconomicAnalyst(
                        user_id=uid,
                        specialization="Macro",
                        organization="IMF",
                        report_access_level="full",
                    )
                )

        db.flush()
        ok = verify_password(plain, user.password)
        detected = detect_role(db, uid)
        print(f"OK {email} role={detected} verify={ok}")

    db.commit()
    print("Done — use the passwords above on the login page with the matching role tab.")
finally:
    db.close()
