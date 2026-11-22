"""
Unified natural-language query plan (Groq structured output + rule fallback).

kind:
  aggregate — forward to existing AnalyticsSpec / ORM aggregates
  browse    — list / filter rows from a whitelisted entity
  mutate    — create / update / delete (assistant: admin only)
  action    — process disbursement / repayment (assistant: admin only)
  unsupported — cannot be fulfilled safely
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.analytics_schemas.analytics import AnalyticsSpec, FilterSpec


class NLQueryPlan(BaseModel):
    kind: str = Field(
        default="aggregate",
        description="aggregate | browse | mutate | action | unsupported",
    )
    note: str = Field(default="", description="Reason if unsupported or extra context")
    export_format: Optional[str] = Field(
        default=None,
        description='Set to "pdf" or "csv" when the user wants a file download',
    )

    aggregate: Optional[AnalyticsSpec] = None

    browse_entity: str = Field(default="", description="e.g. currency, country, loan")
    browse_filters: List[FilterSpec] = Field(default_factory=list)
    browse_order_field: str = ""
    browse_order_dir: str = "asc"
    browse_limit: int = Field(default=200, ge=1, le=500)
    browse_template: str = Field(
        default="",
        description=(
            "Optional templates: loan_extended, loan_country_currency_os, txn_jan_through_march, "
            "txn_debits_outflows, loans_all_installments_paid, loans_missing_condition_mappings, "
            "loans_installments_overdue, installments_partial_only, loan_mapped_conditions_sheet, "
            "scalar_sum_repaid_by_loan, fx_latest_pair, econ_records_high_gdp, econ_inflation_above_threshold, "
            "econ_snapshot_country, inflation_compare_europe_region"
        ),
    )
    browse_projection: List[str] = Field(
        default_factory=list,
        description="If non-empty: include only these keys, in this order.",
    )
    browse_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Template-specific knobs (GDP floor, fx_from/to, loan_id, …).",
    )

    mutate_entity: str = ""
    mutate_op: str = Field(default="", description="create | update | delete")
    mutate_keys: Dict[str, Any] = Field(default_factory=dict)
    mutate_body: Dict[str, Any] = Field(default_factory=dict)

    action: str = Field(default="", description="process_disbursement | process_repayment")
    action_body: Dict[str, Any] = Field(default_factory=dict)
