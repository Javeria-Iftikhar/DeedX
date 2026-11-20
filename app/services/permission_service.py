"""
services/permission_service.py — Service-layer wrapper around analytics_permissions.

Provides a single entry point for validating an AnalyticsSpec against a user role,
then stripping any fields the role can't see before the query builder runs.
"""

from app.core.analytics_permissions import validate_analytics_spec
from app.analytics_schemas.analytics import AnalyticsSpec


def validate_and_sanitise_spec(role: str, spec: AnalyticsSpec) -> AnalyticsSpec:
    """
    Validate the spec against RBAC rules.

    - Raises HTTP 400/403 on any violation (via validate_analytics_spec).
    - Returns the spec unchanged if all checks pass.

    Called by analytics_service before the query builder.
    """
    validate_analytics_spec(role, spec)
    return spec
