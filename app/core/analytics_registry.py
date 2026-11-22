"""
core/analytics_registry.py — Registry mapping module names to ORM models
and their joinable relationships.

ARCHITECTURE:
  The registry is the single place that knows which SQLAlchemy model
  backs each analytics module, what columns exist, and what safe JOINs
  are allowed. The query builder reads only from here — it never
  constructs table names from user input.

SECURITY:
  - Module names are looked up in this dict; unknown names → rejected.
  - Join paths are predefined; arbitrary joins are impossible.
  - This registry does NOT expose schema to users.
"""

from typing import Any, Dict, List, Optional
from app import models


# ── Module registry ────────────────────────────────────────────────────────────
#
# Each entry:
#   model         : Primary SQLAlchemy ORM model class
#   pk            : Primary key column attribute name
#   date_field    : Default date/time column for time-range filters
#   group_fields  : Columns that can be used in GROUP BY
#   metric_fields : Columns that can be aggregated
#   joins         : List of predefined safe join specs (see below)

ANALYTICS_REGISTRY: Dict[str, Dict[str, Any]] = {

    "loan": {
        "model": models.Loan,
        "pk": "loan_id",
        "date_field": "start_date",
        "group_fields": ["status", "country_name", "program_name", "currency_code"],
        "metric_fields": ["loan_amount", "interest_rate", "no_of_installments"],
        "joins": [
            {
                "join_model": models.Country,
                "left_col": "country_id",
                "right_col": "country_id",
                "alias_field": "country_name",       # exposed field name
                "source_col": models.Country.name,   # actual column
            },
            {
                "join_model": models.LoanProgram,
                "left_col": "program_id",
                "right_col": "program_id",
                "alias_field": "program_name",
                "source_col": models.LoanProgram.program_name,
            },
        ],
    },

    "economic": {
        "model": models.EconomicIndicator,
        "pk": "indicator_id",
        "date_field": "record_date",
        "group_fields": ["country_name", "region"],
        "metric_fields": [
            "CPI", "industrial_output", "agricultural_output",
            "services_output", "money_supply", "interest_rate",
            "exchange_rate", "GDP", "inflation",
        ],
        "joins": [
            {
                "join_model": models.Country,
                "left_col": "country_id",
                "right_col": "country_id",
                "alias_field": "country_name",
                "source_col": models.Country.name,
                "extra_aliases": {"region": models.Country.region},
            },
            {
                # EconomicRecord extends EconomicIndicator 1:1 (GDP, inflation live here)
                "join_model": models.EconomicRecord,
                "left_col": "indicator_id",
                "right_col": "indicator_id",
                "alias_field": None,
                "source_col": None,
                "include_when_any_field": ["GDP", "inflation", "record_id"],
            },
        ],
    },

    "repayment": {
        "model": models.Repayment,
        "pk": "repayment_no",
        "date_field": "payment_date",
        "group_fields": ["loan_id", "country_name"],
        "metric_fields": ["amount_paid", "outstanding_balance"],
        "joins": [
            {
                # Bridge to Loan so we can reach Country.name as country_name
                "join_model": models.Loan,
                "left_join_model": None,
                "left_col": "loan_id",
                "right_col": "loan_id",
                "alias_field": None,
                "source_col": None,
                "include_when_any_field": ["country_name"],
            },
            {
                "join_model": models.Country,
                "left_join_model": models.Loan,
                "left_col": "country_id",
                "right_col": "country_id",
                "alias_field": "country_name",
                "source_col": models.Country.name,
            },
        ],
    },

    "installment": {
        "model": models.Installment,
        "pk": "installment_no",
        "date_field": "due_date",
        "group_fields": ["loan_id", "status", "country_name"],
        "metric_fields": ["amount_due", "amount_paid"],
        "joins": [
            {
                "join_model": models.Loan,
                "left_join_model": None,
                "left_col": "loan_id",
                "right_col": "loan_id",
                "alias_field": None,
                "source_col": None,
                "include_when_any_field": ["country_name"],
            },
            {
                "join_model": models.Country,
                "left_join_model": models.Loan,
                "left_col": "country_id",
                "right_col": "country_id",
                "alias_field": "country_name",
                "source_col": models.Country.name,
            },
        ],
    },

    "transaction": {
        "model": models.FinancialTransaction,
        "pk": "transaction_id",
        "date_field": "transaction_date",
        "group_fields": ["transaction_type", "currency_code"],
        "metric_fields": ["amount"],
        "joins": [],
    },

    "user": {
        "model": models.User,
        "pk": "user_id",
        "date_field": None,
        "group_fields": ["name", "email"],
        "metric_fields": ["user_id"],
        "joins": [],
    },

    # Cross-table country analytics: GDP/inflation (economic) + loan_amount (loans)
    "country": {
        "model": models.Country,
        "pk": "country_id",
        "date_field": None,
        "group_fields": ["country_name", "region", "currency_code"],
        "metric_fields": [
            "population", "GDP", "inflation", "CPI", "loan_amount",
            "interest_rate", "amount_paid", "outstanding_balance",
        ],
        "virtual_aliases": {
            "country_name": models.Country.name,
        },
        "joins": [
            {
                "join_model": models.Loan,
                "left_col": "country_id",
                "right_col": "country_id",
                "alias_field": None,
                "source_col": None,
                "include_when_any_field": [
                    "loan_amount", "loan_id", "status", "interest_rate",
                    "no_of_installments", "program_name",
                ],
            },
            {
                "join_model": models.LoanProgram,
                "left_join_model": models.Loan,
                "left_col": "program_id",
                "right_col": "program_id",
                "alias_field": "program_name",
                "source_col": models.LoanProgram.program_name,
                "include_when_any_field": ["program_name"],
            },
            {
                "join_model": models.EconomicIndicator,
                "left_col": "country_id",
                "right_col": "country_id",
                "alias_field": None,
                "source_col": None,
                "include_when_any_field": [
                    "indicator_id", "record_date", "CPI", "industrial_output",
                    "agricultural_output", "services_output", "money_supply",
                    "interest_rate", "exchange_rate",
                ],
            },
            {
                "join_model": models.EconomicRecord,
                "left_join_model": models.EconomicIndicator,
                "left_col": "indicator_id",
                "right_col": "indicator_id",
                "alias_field": None,
                "source_col": None,
                "include_when_any_field": ["GDP", "inflation", "record_id"],
            },
            {
                "join_model": models.Repayment,
                "left_join_model": models.Loan,
                "left_col": "loan_id",
                "right_col": "loan_id",
                "alias_field": None,
                "source_col": None,
                "include_when_any_field": ["amount_paid", "outstanding_balance", "repayment_no"],
            },
            {
                "join_model": models.Installment,
                "left_join_model": models.Loan,
                "left_col": "loan_id",
                "right_col": "loan_id",
                "alias_field": None,
                "source_col": None,
                "include_when_any_field": ["amount_due", "amount_paid", "installment_no", "due_date"],
            },
        ],
    },
}


def get_module(module_name: str) -> Optional[Dict[str, Any]]:
    """Return registry entry or None if module is unknown."""
    return ANALYTICS_REGISTRY.get(module_name)


def list_modules() -> List[str]:
    return list(ANALYTICS_REGISTRY.keys())
