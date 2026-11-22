"""
core/analytics_permissions.py — RBAC enforcement layer for analytics.

All permission checks for the dynamic analytics system go through here.
Routers and services call these functions; they never implement their own
permission logic.
"""

from fastapi import HTTPException, status
from app.core.allowed_fields import (
    is_module_allowed,
    is_field_allowed,
    ALLOWED_AGGREGATIONS,
    ALLOWED_OPERATORS,
    ALLOWED_CHART_TYPES,
    ALLOWED_SORT_DIRECTIONS,
    SUPPORTED_MODULES,
)
from app.analytics_schemas.analytics import AnalyticsSpec, MetricSpec, FilterSpec


def enforce_module_access(role: str, module: str) -> None:
    """Raise 403 if this role cannot query this module."""
    if module not in SUPPORTED_MODULES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown module '{module}'. Supported: {sorted(SUPPORTED_MODULES)}",
        )
    if not is_module_allowed(role, module):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' is not permitted to access module '{module}'.",
        )


def enforce_field_access(role: str, module: str, field: str) -> None:
    """Raise 403 if this role cannot access this field in this module."""
    if not is_field_allowed(role, module, field):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Field '{field}' is not permitted for role '{role}' in module '{module}'.",
        )


def enforce_aggregation(aggregation: str) -> None:
    """Raise 400 if the aggregation function is not on the allowlist."""
    if aggregation.lower() not in ALLOWED_AGGREGATIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aggregation '{aggregation}' is not allowed. "
                   f"Allowed: {sorted(ALLOWED_AGGREGATIONS)}",
        )


def enforce_operator(operator: str) -> None:
    """Raise 400 if the filter operator is not on the allowlist."""
    norm = (operator or "").strip().lower()
    if norm not in ALLOWED_OPERATORS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Operator '{operator}' is not allowed. "
                   f"Allowed: {sorted(ALLOWED_OPERATORS)}",
        )


def enforce_chart_type(chart_type: str) -> None:
    """Raise 400 if the chart type is unsupported."""
    if chart_type not in ALLOWED_CHART_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chart type '{chart_type}' is not supported. "
                   f"Supported: {sorted(ALLOWED_CHART_TYPES)}",
        )


def enforce_sort_direction(direction: str) -> None:
    if direction.lower() not in ALLOWED_SORT_DIRECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sort direction '{direction}' is invalid. Use 'asc' or 'desc'.",
        )


def validate_analytics_spec(role: str, spec: "AnalyticsSpec") -> None:
    """
    Full validation of a parsed AnalyticsSpec against role permissions.
    Raises HTTP 400/403 on the first violation found.
    """
    # 1. Module access
    enforce_module_access(role, spec.module)

    # 2. Metrics
    for metric in spec.metrics:
        enforce_field_access(role, spec.module, metric.field)
        enforce_aggregation(metric.aggregation)

    # 3. Group-by fields
    for field in spec.group_by:
        enforce_field_access(role, spec.module, field)

    # 4. Filters (operators canonicalised lowercase in AnalyticsSpec preprocessing)
    for f in spec.filters:
        enforce_field_access(role, spec.module, f.field)
        enforce_operator((f.operator or "").strip().lower())

    # 5. Sort
    if spec.sort:
        enforce_field_access(role, spec.module, spec.sort.field)
        enforce_sort_direction(spec.sort.direction)

    # 6. Chart type
    if spec.chart_type:
        enforce_chart_type(spec.chart_type)

    # 7. Limit sanity
    if spec.limit is not None and (spec.limit < 1 or spec.limit > 1000):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 1000.",
        )
