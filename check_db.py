"""Quick check: can the app connect to PostgreSQL? Run: python check_db.py"""
import sys

def main():
    try:
        from app.database import DATABASE_URL, engine
        # Hide password in output
        safe = DATABASE_URL.split("@", 1)
        print("DATABASE_URL:", safe[0].rsplit(":", 1)[0] + ":***@" + safe[1] if len(safe) == 2 else "(hidden)")
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        print("OK — PostgreSQL connection works.")
        return 0
    except Exception as e:
        print("FAILED —", e, file=sys.stderr)
        print("\nFix: edit app/.env and set DATABASE_URL with your real postgres password.", file=sys.stderr)
        print("Then create the database in pgAdmin or psql: CREATE DATABASE imf_db;", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
