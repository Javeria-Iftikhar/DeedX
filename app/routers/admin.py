"""
routers/admin.py  — thin router that re-uses the user router's admin/officer/analyst endpoints.
Included in main.py separately so Swagger groups them under an "Admin" prefix if desired.
This file intentionally stays minimal — all logic is in routers/users.py.
"""

from fastapi import APIRouter
router = APIRouter(tags=["Admin"])

# All admin/officer/analyst routes are already on routers/users.py.
# Add any admin-specific aggregate routes here in the future.
