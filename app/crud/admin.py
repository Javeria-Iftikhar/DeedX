"""
crud/admin.py  —  thin re-exports so the admin router has its own crud module
(the heavy lifting is in crud/users.py)
"""

from app.crud.users import (
    create_admin, get_admins, get_admin, delete_admin,
    create_officer, get_officers, get_officer, delete_officer,
    create_analyst, get_analysts, get_analyst, delete_analyst,
)

__all__ = [
    "create_admin", "get_admins", "get_admin", "delete_admin",
    "create_officer", "get_officers", "get_officer", "delete_officer",
    "create_analyst", "get_analysts", "get_analyst", "delete_analyst",
]
