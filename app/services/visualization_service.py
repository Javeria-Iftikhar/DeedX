"""
services/visualization_service.py — Converts raw query results and an AnalyticsSpec
into a user-facing DashboardResponse with chart configuration.

RESPONSIBILITY:
  - Decides x-axis, y-axis, chart title, and legend based on spec shape.
  - Formats the raw rows into the final dashboard data list.
  - Does NOT query the database.
"""

from typing import Any, Dict, List, Optional

from app.analytics_schemas.analytics import AnalyticsSpec
from app.analytics_schemas.dashboard import DashboardResponse, DashboardMetadata


# ── Title generation ───────────────────────────────────────────────────────────

_MODULE_LABELS = {
    "loan":        "Loan",
    "economic":    "Economic",
    "repayment":   "Repayment",
    "installment": "Installment",
    "transaction": "Transaction",
    "user":        "User",
}

_AGG_LABELS = {
    "count": "Count of",
    "sum":   "Total",
    "avg":   "Average",
    "min":   "Minimum",
    "max":   "Maximum",
}

_FIELD_LABELS = {
    "loan_amount":        "Loan Amount",
    "GDP":                "GDP",
    "inflation":          "Inflation Rate",
    "avg_inflation":      "Average inflation",
    "CPI":                "CPI",
    "exchange_rate":      "Exchange Rate",
    "interest_rate":      "Interest Rate",
    "amount_paid":        "Amount Paid",
    "outstanding_balance":"Outstanding Balance",
    "amount_due":         "Amount Due",
    "amount":             "Transaction Amount",
    "user_id":            "Users",
    "country_name":       "Country",
    "status":             "Status",
    "program_name":       "Program",
    "transaction_type":   "Transaction Type",
    "loan_id":            "Loan",
    "record_date":        "Date",
}


def _field_label(field: str) -> str:
    return _FIELD_LABELS.get(field, field.replace("_", " ").title())


def _build_title(spec: AnalyticsSpec) -> str:
    metric = spec.metrics[0]
    agg_label   = _AGG_LABELS.get(metric.aggregation, metric.aggregation.title())
    field_label = _field_label(metric.field)
    module_label = _MODULE_LABELS.get(spec.module, spec.module.title())

    title = f"{agg_label} {field_label}"

    if spec.group_by:
        group_label = _field_label(spec.group_by[0])
        title += f" by {group_label}"

    filters_desc = []
    for f in spec.filters:
        if f.operator == "=" and isinstance(f.value, str):
            filters_desc.append(f.value.title())

    if filters_desc:
        title += " (" + ", ".join(filters_desc) + ")"

    return title


# ── Axis detection ─────────────────────────────────────────────────────────────

def _detect_x_axis(spec: AnalyticsSpec) -> Optional[str]:
    """X-axis is the first group_by field; or date if filtering by time."""
    if spec.group_by:
        return spec.group_by[0]
    date_fields = {"record_date", "start_date", "payment_date", "transaction_date", "due_date"}
    for f in spec.filters:
        if f.field in date_fields:
            return f.field
    return None


def _detect_y_axis(spec: AnalyticsSpec) -> Optional[str]:
    """Y-axis is the label of the first aggregated metric."""
    if spec.metrics:
        m = spec.metrics[0]
        return f"{m.aggregation}_{m.field}"
    return None


# ── Chart type override ────────────────────────────────────────────────────────

def _pick_chart_type(spec: AnalyticsSpec) -> str:
    """
    If the spec already carries a chart type (from user intent or parser),
    respect it. Otherwise infer from the shape of the query.
    """
    if spec.chart_type:
        return spec.chart_type
    # Time series → line
    date_fields = {"record_date", "start_date", "payment_date", "transaction_date"}
    if any(g in date_fields for g in spec.group_by):
        return "line"
    # Category with multiple groups → bar
    if spec.group_by:
        return "bar"
    # Metrics only → table
    return "table"


# ── Public entry point ─────────────────────────────────────────────────────────

def build_dashboard_response(
    spec: AnalyticsSpec,
    raw_rows: List[Dict[str, Any]],
    original_query: str = "",
    summary: Optional[str] = None,
) -> DashboardResponse:
    """
    Assemble a DashboardResponse from a validated spec and executed rows.
    """
    chart_type = _pick_chart_type(spec)
    x_axis     = _detect_x_axis(spec)
    y_axis     = _detect_y_axis(spec)
    title      = _build_title(spec)

    metadata = DashboardMetadata(
        module=spec.module,
        applied_filters=[
            {"field": f.field, "operator": f.operator, "value": f.value}
            for f in spec.filters
        ],
        group_by=spec.group_by,
        row_count=len(raw_rows),
    )

    return DashboardResponse(
        title=title,
        chart_type=chart_type,
        x_axis=x_axis,
        y_axis=y_axis,
        data=raw_rows,
        summary=summary,
        metadata=metadata,
    )
