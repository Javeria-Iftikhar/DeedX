"""
reseed_dev.py — Wipe and reload the canonical seed_data.py dataset.

    python reseed_dev.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.seed_data import seed_data


def main():
    print("Force re-seeding canonical IMF dataset…")
    seed_data(force=True)
    try:
        from ensure_role_users import ensure_role_users
        ensure_role_users()
    except Exception as exc:
        print(f"Note: dev role users: {exc}")
    print("Done.")


if __name__ == "__main__":
    main()
