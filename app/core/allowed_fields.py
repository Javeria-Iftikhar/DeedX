"""
core/allowed_fields.py — Centralized field whitelist per role per module.

This is the single source of truth for what fields, aggregations, and
filter operators each role may use. Nothing else in the codebase defines
access rules — they all delegate here.

SECURITY:
  - Any field NOT in this registry is REJECTED outright.
  - Roles are additive: Admin sees everything; others are scoped.
  - This file must be reviewed on every schema change.
"""

from typing import Dict, List, Set

# ── Supported aggregation functions ──────────────────────────────────────────

ALLOWED_AGGREGATIONS: Set[str] = {"count", "sum", "avg", "min", "max"}

# ── Supported filter operators ────────────────────────────────────────────────

ALLOWED_OPERATORS: Set[str] = {"=", "!=", ">", "<", ">=", "<=", "in", "ilike"}

# ── Supported chart types ─────────────────────────────────────────────────────

ALLOWED_CHART_TYPES: Set[str] = {"bar", "line", "pie", "table", "area"}

# ── Supported sort directions ─────────────────────────────────────────────────

ALLOWED_SORT_DIRECTIONS: Set[str] = {"asc", "desc"}

# ── Supported modules (top-level query targets) ───────────────────────────────

SUPPORTED_MODULES: Set[str] = {
    "loan", "economic", "repayment", "transaction", "user", "installment", "country",
}

# ── Per-role, per-module field whitelists ─────────────────────────────────────
#
# Structure:
#   ALLOWED_FIELDS[role][module] = [list of safe field names]
#
# A field name maps to a column on the primary model for that module
# (see analytics_registry.py for model-to-module mapping).

ALLOWED_FIELDS: Dict[str, Dict[str, List[str]]] = {

    # ── ADMIN — full access ────────────────────────────────────────────────
    "admin": {
        "loan": [
            "loan_id", "loan_amount", "interest_rate", "start_date",
            "end_date", "status", "no_of_installments",
            "country_name",   # joined from Country
            "program_name",   # joined from LoanProgram
        ],
        "economic": [
            "indicator_id", "record_date", "CPI", "industrial_output",
            "agricultural_output", "services_output", "money_supply",
            "interest_rate", "exchange_rate",
            "GDP", "inflation",
            "country_name",   # joined from Country
            "region",         # Country.region via same join — Europe / geography filters
        ],
        "repayment": [
            "loan_id", "repayment_no", "amount_paid",
            "payment_date", "outstanding_balance",
            "country_name",
        ],
        "installment": [
            "loan_id", "installment_no", "due_date",
            "amount_due", "amount_paid", "status",
            "country_name",
        ],
        "transaction": [
            "transaction_id", "amount", "transaction_type",
            "transaction_date", "reference",
        ],
        "user": [
            "user_id", "name", "email",
        ],
        "country": [
            "country_id", "country_name", "region", "population", "currency_code",
            "GDP", "inflation", "CPI", "loan_amount", "interest_rate",
            "amount_paid", "outstanding_balance", "status",
            "record_date", "program_name",
        ],
    },

    # ── OFFICER — loan/financial scope ────────────────────────────────────
    "officer": {
        "loan": [
            "loan_id", "loan_amount", "interest_rate", "start_date",
            "end_date", "status", "no_of_installments",
            "country_name",
            "program_name",
        ],
        "repayment": [
            "loan_id", "repayment_no", "amount_paid",
            "payment_date", "outstanding_balance",
            "country_name",
        ],
        "installment": [
            "loan_id", "installment_no", "due_date",
            "amount_due", "amount_paid", "status",
            "country_name",
        ],
        "transaction": [
            "transaction_id", "amount", "transaction_type",
            "transaction_date", "reference",
        ],
        "country": [
            "country_id", "country_name", "region", "currency_code",
            "loan_amount", "status", "amount_paid", "outstanding_balance",
        ],
        # No: user, economic, audit
    },

    # ── ANALYST — economic scope ───────────────────────────────────────────
    "analyst": {
        "economic": [
            "indicator_id", "record_date", "CPI", "industrial_output",
            "agricultural_output", "services_output", "money_supply",
            "interest_rate", "exchange_rate",
            "GDP", "inflation",
            "country_name",
            "region",
        ],
        "country": [
            "country_id", "country_name", "region", "GDP", "inflation", "CPI",
            "record_date",
        ],
        # No: loan, repayment, installment, transaction, user, audit
    },
}


def get_allowed_fields(role: str, module: str) -> List[str]:
    """Return the whitelist for a role+module pair, or [] if not permitted."""
    return ALLOWED_FIELDS.get(role, {}).get(module, [])


def is_field_allowed(role: str, module: str, field: str) -> bool:
    return field in get_allowed_fields(role, module)


def is_module_allowed(role: str, module: str) -> bool:
    return module in ALLOWED_FIELDS.get(role, {})
