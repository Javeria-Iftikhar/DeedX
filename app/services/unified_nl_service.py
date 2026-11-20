"""
Unified natural-language execution layer.

Handles:
- aggregate (ORM-safe rollup analytics)
- browse    (row-level entity listing)
- mutate    (admin-only create/update/delete)
- action    (admin-only disbursement / repayment workflows)

Key design principles:
1. NO hardcoded country names or region member lists anywhere.
   All geography is resolved from DISTINCT `country.region` in the live DB.
2. Multi-turn conversation is threaded through every AI call so follow-up
   questions ("also show GDP", "now export as PDF") work correctly.
3. Export intent (PDF / CSV) detected in the NLQueryPlan is routed to the
   existing export endpoint and the URL is surfaced in the response.
4. Chart type is inferred from user wording (bar / line / pie / table).
5. The permission layer and ORM query builder remain the single execution path
   for aggregates — this service only selects kind + structured fields.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from fastapi import HTTPException, status
from sqlalchemy import and_, asc, desc, exists, extract, func, not_, or_
from sqlalchemy.orm import Session, aliased

from app import models, schemas
from app.analytics_schemas.analytics import AnalyticsSpec, FilterSpec, MetricSpec, SortSpec
from app.core.allowed_fields import is_field_allowed
from app.analytics_schemas.dashboard import DashboardMetadata, DashboardResponse
from app.analytics_schemas.nl_plan import NLQueryPlan
from app.audit import write_audit_log
from app.crud import economic as crud_econ
from app.crud import loans as crud_loans
from app.crud import users as crud_users
from app.services import analytics_llm_service as llm_svc
from app.services.query_builder_service import build_and_execute, _serialise
from app.services.query_parser_service import parse_natural_language_query, _check_injection
from app.services.permission_service import validate_and_sanitise_spec
from app.services.visualization_service import build_dashboard_response

logger = logging.getLogger(__name__)

ADMIN_ASSISTANT_ONLY = (
    "Create, update, delete, and disbursement/repayment actions via the assistant "
    "are restricted to administrators."
)

# ---------------------------------------------------------------------------
# Entity → Model mapping
# ---------------------------------------------------------------------------

ENTITY_MODELS: Dict[str, Type] = {
    "currency": models.Currency,
    "country": models.Country,
    "loan_program": models.LoanProgram,
    "imf_account": models.IMFAccount,
    "loan": models.Loan,
    "loan_condition": models.LoanCondition,
    "loan_condition_mapping": models.LoanConditionMapping,
    "mapping": models.LoanConditionMapping,
    "loan_disbursement": models.LoanDisbursement,
    "repayment": models.Repayment,
    "installment": models.Installment,
    "economic_indicator": models.EconomicIndicator,
    "economic_record": models.EconomicRecord,
    "exchange_rate": models.ExchangeRate,
    "financial_transaction": models.FinancialTransaction,
    "audit_log": models.AuditLog,
    "users": models.User,
    "admin": models.Admin,
    "officer": models.Officer,
    "economicanalyst": models.EconomicAnalyst,
}

ADMIN_ENTITIES: Set[str] = set(ENTITY_MODELS.keys()) - {"mapping"}

OFFICER_ENTITIES: Set[str] = {
    "currency", "country", "loan_program", "imf_account", "loan",
    "loan_condition", "loan_condition_mapping", "loan_disbursement",
    "repayment", "installment", "financial_transaction", "audit_log",
}

ANALYST_ENTITIES: Set[str] = {
    "country", "economic_indicator", "economic_record", "exchange_rate", "audit_log",
}

_HIDDEN_USER_COLS = {"password"}


# ---------------------------------------------------------------------------
# Geography helpers — all resolved from the live DB, nothing hardcoded
# ---------------------------------------------------------------------------

def _distinct_region_labels_matching(db: Session, region_keyword: str) -> List[str]:
    """
    Return DISTINCT `country.region` values that contain `region_keyword`
    (case-insensitive).  All geography comes from the DB — no static lists.
    """
    rows = (
        db.query(models.Country.region)
        .distinct()
        .filter(models.Country.region.isnot(None))
        .filter(models.Country.region != "")
        .filter(models.Country.region.ilike(f"%{region_keyword}%"))
        .all()
    )
    return [str(rv[0]).strip() for rv in rows if rv[0]]


def _country_names_for_regions(db: Session, regions: List[str]) -> List[str]:
    """Return DISTINCT `country.name` values whose `region` is in `regions`."""
    if not regions:
        return []
    rows = (
        db.query(models.Country.name)
        .filter(models.Country.region.in_(regions))
        .distinct()
        .all()
    )
    return sorted({str(nm[0]) for nm in rows if nm[0]})


def _resolve_region_filter_to_country_names(
    db: Session, region_keyword: str
) -> List[str]:
    """
    Given a keyword like "Europe", return all country names whose stored
    region matches — fully dynamic, nothing hardcoded.
    """
    regions = _distinct_region_labels_matching(db, region_keyword)
    return _country_names_for_regions(db, regions)


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def _flatten_nl_context_lower(
    current_q: str, conversation: Optional[List[Dict[str, Any]]]
) -> str:
    """Flat lowercase string of all conversation turns + current query."""
    parts: List[str] = []
    if conversation:
        for turn in conversation[-12:]:
            c = str(turn.get("content", "")).strip()
            if c:
                parts.append(c)
    parts.append(current_q.strip())
    return " ".join(parts).lower()


def _nl_wants_line_chart(ctx: str) -> bool:
    return bool(
        re.search(
            r"(?:line[\s\-]?(?:graph|chart|plot)|\bline\s+graph\b|"
            r"as\s+a\s+line|give\s+me\s+(?:a\s+)?line|create\s+(?:a\s+)?line|"
            r"draw\s+(?:a\s+)?line|show\s+(?:a\s+)?line|make\s+(?:a\s+)?line)",
            ctx,
            re.IGNORECASE,
        )
    )


def _nl_wants_pie_chart(ctx: str) -> bool:
    return bool(
        re.search(
            r"(?:pie[\s\-]?(?:graph|chart)|\bpie\s+graph\b|"
            r"give\s+me\s+(?:a\s+)?pie|create\s+(?:a\s+)?pie|"
            r"draw\s+(?:a\s+)?pie|show\s+(?:a\s+)?pie|make\s+(?:a\s+)?pie)",
            ctx,
            re.IGNORECASE,
        )
    )


def _nl_wants_visual_chart(ctx: str) -> bool:
    if _nl_wants_line_chart(ctx) or _nl_wants_pie_chart(ctx):
        return True
    return any(
        w in ctx
        for w in (
            "graph", "chart", "plot", "bar chart", "bar graph",
            "histogram", "visuali", "diagram",
        )
    )


def _detect_export_format(current_query: str) -> Optional[str]:
    """Return ``pdf`` or ``csv`` only when the *current* message asks to export/download."""
    ctx_l = current_query.strip().lower()
    if not ctx_l:
        return None
    has_pdf = "pdf" in ctx_l
    has_csv = "csv" in ctx_l
    wants_file = bool(
        re.search(
            r"\b(export|download|save)\b|"
            r"\bas\s+(?:a\s+)?(?:pdf|csv)\b|"
            r"\bto\s+(?:a\s+)?(?:pdf|csv)\b|"
            r"\bin\s+(?:a\s+)?(?:pdf|csv)\b|"
            r"\bgenerate\s+(?:a\s+)?(?:pdf|csv)\b",
            ctx_l,
        )
    )
    if not wants_file and not (has_pdf or has_csv):
        return None
    if has_pdf:
        return "pdf"
    if has_csv:
        return "csv"
    if wants_file:
        return "csv"
    return None


def _apply_nl_chart_overrides(context_lower: str, dash: DashboardResponse) -> DashboardResponse:
    """Force chart_type from explicit NL wording (line graph / pie graph, etc.)."""
    if not dash.data:
        return dash
    if _nl_wants_line_chart(context_lower):
        return dash.model_copy(update={"chart_type": "line"})
    if _nl_wants_pie_chart(context_lower):
        return dash.model_copy(update={"chart_type": "pie"})
    return dash


def _attach_export_format(dash: DashboardResponse, export_format: Optional[str]) -> DashboardResponse:
    if not export_format:
        return dash
    fmt = export_format.strip().lower()
    if fmt not in ("pdf", "csv"):
        return dash
    return dash.model_copy(update={"export_format": fmt})


# ---------------------------------------------------------------------------
# Aggregate spec enrichment
# ---------------------------------------------------------------------------

def _expand_scalar_aggregate_for_visualization(
    role: str, context_lower: str, spec: AnalyticsSpec
) -> AnalyticsSpec:
    """
    A scalar aggregate (no group_by) cannot produce a meaningful chart.
    When the user asks for a visualisation, try to add a group_by dimension.

    Dimensions are picked dynamically from what is allowed for this role/module —
    we prefer country_name if available, then any other allowed string field.
    """
    if spec.group_by:
        return spec  # already has grouping
    if len(spec.metrics) != 1:
        return spec

    if not (
        _nl_wants_visual_chart(context_lower)
        or _nl_wants_line_chart(context_lower)
        or _nl_wants_pie_chart(context_lower)
    ):
        return spec

    from app.core.allowed_fields import ALLOWED_FIELDS

    mod = spec.module.strip().lower()
    allowed_fields: List[str] = list(ALLOWED_FIELDS.get(role, {}).get(mod, []))

    # Prefer country_name as the grouping dimension for most modules
    dim: Optional[str] = None
    if "country_name" in allowed_fields and is_field_allowed(role, mod, "country_name"):
        dim = "country_name"
    else:
        # Pick any non-numeric-looking field that isn't the metric field
        metric_field = spec.metrics[0].field
        for f in allowed_fields:
            if f != metric_field and not any(
                tok in f for tok in ("amount", "rate", "balance", "gdp", "cpi", "inflation", "id")
            ):
                dim = f
                break

    if dim is None:
        return spec

    wants_line = _nl_wants_line_chart(context_lower)
    wants_pie = _nl_wants_pie_chart(context_lower)
    chart = "line" if wants_line else ("pie" if wants_pie else "bar")
    lim = max(min(int(spec.limit or 50), 1_000), 50)

    return spec.model_copy(update={"group_by": [dim], "chart_type": chart, "limit": lim})


def _prefer_aggregate_chart_type(context_lower: str, spec: AnalyticsSpec) -> AnalyticsSpec:
    """Honour explicit chart-type keywords; infer defaults when viz wording is present."""
    if _nl_wants_line_chart(context_lower) and spec.group_by:
        return spec.model_copy(update={"chart_type": "line"})
    if _nl_wants_pie_chart(context_lower) and spec.group_by:
        return spec.model_copy(update={"chart_type": "pie"})
    if not _nl_wants_visual_chart(context_lower):
        return spec
    if spec.chart_type and spec.chart_type not in ("table", ""):
        return spec
    if not spec.group_by:
        return spec
    if any(g in {"record_date", "start_date", "payment_date", "transaction_date"}
           for g in spec.group_by):
        return spec.model_copy(update={"chart_type": "line"})
    return spec.model_copy(update={"chart_type": "bar"})


def _inject_region_filters_from_db(
    db: Session, context_lower: str, spec: AnalyticsSpec
) -> AnalyticsSpec:
    """
    When any filter targets 'region' (ilike), resolve it to an explicit
    country_name IN [...] filter by querying the DB.

    This is the ONLY place geography is resolved — no hardcoded lists anywhere.
    """
    region_filters = [
        f for f in spec.filters
        if f.field.strip().lower() == "region" and f.operator.lower() == "ilike"
    ]
    if not region_filters:
        return spec

    other_filters = [f for f in spec.filters if f.field.strip().lower() != "region"]
    new_filters: List[FilterSpec] = list(other_filters)

    for rf in region_filters:
        # Extract the keyword from the ilike pattern (strip % wildcards)
        keyword = str(rf.value).strip("%").strip()
        names = _resolve_region_filter_to_country_names(db, keyword)
        if names:
            new_filters.append(
                FilterSpec(field="country_name", operator="in", value=list(names))
            )
        else:
            # Fallback: keep a country_name ilike filter so results at least narrow
            new_filters.append(
                FilterSpec(field="country_name", operator="ilike", value=f"%{keyword}%")
            )

    return spec.model_copy(update={"filters": new_filters})


# ---------------------------------------------------------------------------
# Browse helpers
# ---------------------------------------------------------------------------

def _entities_for_role(role: str) -> Set[str]:
    r = (role or "").lower().strip()
    if r == "admin":
        return ADMIN_ENTITIES
    if r == "officer":
        return OFFICER_ENTITIES
    if r == "analyst":
        return ANALYST_ENTITIES
    return set()


def _orm_row_dict(obj, hide: Optional[Set[str]] = None) -> Dict[str, Any]:
    hide = hide or set()
    return {
        col: _serialise(getattr(obj, col))
        for col in obj.__table__.columns.keys()
        if col not in hide
    }


def _apply_column_filter(query, model, f: FilterSpec):
    col = getattr(model, f.field)
    op = llm_svc._canonical_filter_op(f.operator).lower().strip()
    val = f.value
    ops = {
        "=": lambda: query.filter(col == val),
        "!=": lambda: query.filter(col != val),
        ">": lambda: query.filter(col > val),
        "<": lambda: query.filter(col < val),
        ">=": lambda: query.filter(col >= val),
        "<=": lambda: query.filter(col <= val),
        "in": lambda: query.filter(col.in_(val if isinstance(val, (list, tuple)) else [val])),
        "ilike": lambda: query.filter(col.ilike(str(val))),
    }
    if op not in ops:
        raise HTTPException(status_code=400, detail=f"Unsupported browse operator: {f.operator}")
    return ops[op]()


def _rbac_can_browse_entity(role: str, ent: str) -> None:
    ent = ent.strip().lower()
    if ent == "mapping":
        ent = "loan_condition_mapping"
    if ent not in _entities_for_role(role):
        raise HTTPException(status_code=403, detail=f"Role '{role}' cannot browse '{ent}'.")


def _reshape_row_ordered(keys_in_order: List[str], raw: Dict[str, Any]) -> Dict[str, Any]:
    return {k: raw.get(k) for k in keys_in_order}


# Groq often emits shorthand column names (e.g. "code") that do not exist on the ORM row.
_ENTITY_BROWSE_DEFAULTS: Dict[str, List[str]] = {
    "currency": ["currency_code", "currency_name", "symbol", "exchange_regime"],
    "country": ["country_id", "country_name", "currency_code", "region", "population"],
    "users": ["user_id", "name", "email"],
    "loan_program": ["program_id", "program_name", "description"],
    "loan": ["loan_id", "country_name", "loan_amount", "currency_code", "status"],
    "exchange_rate": ["rate_date", "from_currency", "to_currency", "rate"],
    "economic_indicator": ["indicator_id", "country_name", "record_date", "CPI", "interest_rate"],
    "economic_record": ["record_id", "GDP", "inflation"],
}

_ENTITY_COLUMN_ALIASES: Dict[str, Dict[str, str]] = {
    "currency": {
        "code": "currency_code",
        "currency": "currency_code",
        "name": "currency_name",
        "currency_name": "currency_name",
        "symbol": "symbol",
        "regime": "exchange_regime",
        "exchange_regime": "exchange_regime",
    },
    "country": {
        "name": "name",
        "country": "name",
        "country_name": "name",
        "code": "currency_code",
        "currency": "currency_code",
        "region": "region",
    },
    "users": {
        "name": "name",
        "email": "email",
        "user": "name",
    },
}


def _resolve_projection_columns(
    entity: str,
    projection: List[str],
    sample: Dict[str, Any],
) -> List[str]:
    """Map planner shorthand to real ORM keys; drop unknown columns."""
    ent = (entity or "").strip().lower()
    aliases = _ENTITY_COLUMN_ALIASES.get(ent, {})
    resolved: List[str] = []
    seen: set = set()
    had_real_column = False
    for col in projection:
        key = (col or "").strip()
        if not key:
            continue
        if key in sample:
            had_real_column = True
        mapped = aliases.get(key, key)
        if mapped in sample and mapped not in seen:
            resolved.append(mapped)
            seen.add(mapped)
    defaults = _ENTITY_BROWSE_DEFAULTS.get(ent)
    # Planner used shorthand only (e.g. code → currency_code) — show full row for list queries
    if resolved and defaults and not had_real_column and len(resolved) < len(defaults):
        return [c for c in defaults if c in sample]
    if resolved:
        return resolved
    defaults = _ENTITY_BROWSE_DEFAULTS.get(ent)
    if defaults:
        return [c for c in defaults if c in sample]
    return list(sample.keys())


def _apply_browse_projection(
    rows: List[Dict[str, Any]],
    projection: Optional[List[str]],
    entity: str = "",
) -> List[Dict[str, Any]]:
    if not projection or not rows:
        return rows
    cols = _resolve_projection_columns(entity, projection, rows[0])
    projected = [_reshape_row_ordered(cols, r) for r in rows]
    # If planner columns were all wrong (e.g. ["code"] → nulls), fall back to defaults
    if projected and all(all(v is None for v in row.values()) for row in projected):
        cols = _resolve_projection_columns(entity, [], rows[0])
        return [_reshape_row_ordered(cols, r) for r in rows]
    return projected


def _browse_scope_tag(plan: NLQueryPlan) -> str:
    """Short scope hint for summary lines."""
    filters = plan.browse_filters
    if not filters:
        if (plan.browse_order_field or "").strip() == "loan_amount":
            direc = "high→low" if (plan.browse_order_dir or "").lower() == "desc" else "low→high"
            return f"by loan amount {direc}"
        return ""
    chunks: List[str] = []
    for f in filters[:4]:
        val_str = str(f.value).strip("% ")
        if f.field == "region":
            chunks.append(val_str.title())
        elif f.field == "country_name":
            chunks.append(val_str)
        elif f.field == "status":
            chunks.append(val_str)
        elif f.field == "loan_id":
            chunks.append(f"loan #{val_str}")
        elif f.field == "interest_rate":
            chunks.append(f"rate {f.operator} {val_str}")
        elif f.field == "population":
            chunks.append(f"population {f.operator} {val_str}")
        else:
            chunks.append(f"{f.field} {f.operator} {val_str}")
    return ", ".join(chunks[:3])


# Fields that live on related tables (FK joins), not on the browse primary model.
_RELATED_FIELD_HINTS: Dict[str, Set[str]] = {
    "country": {
        "loan_id", "loan_amount", "status", "program_name", "interest_rate",
        "amount_paid", "outstanding_balance", "installment_no", "due_date",
        "amount_due", "GDP", "inflation", "indicator_id", "record_date",
    },
    "installment": {"country_name", "loan_amount", "program_name", "region"},
    "repayment": {"country_name", "loan_amount", "program_name", "region", "currency_code"},
    "economic_indicator": {"country_name", "GDP", "inflation", "region"},
    "economic_record": {"country_name", "region", "record_date", "CPI"},
    "loan_disbursement": {"country_name", "loan_amount", "program_name", "region"},
    "financial_transaction": {"country_name", "account_number", "account_type"},
    "loan_condition": {"program_name"},
    "imf_account": set(),
    "exchange_rate": set(),
}


def _model_column_names(model: Type) -> Set[str]:
    return set(model.__table__.columns.keys())


def _browse_needs_join(entity: str, plan: NLQueryPlan) -> bool:
    ent = entity.strip().lower()
    local = _model_column_names(ENTITY_MODELS[ent])
    remote = _RELATED_FIELD_HINTS.get(ent, set())
    names = {f.field for f in plan.browse_filters}
    names.update(plan.browse_projection or [])
    if plan.browse_order_field:
        names.add(plan.browse_order_field.strip())
    for n in names:
        if n in remote or (n not in local and n not in {"country_name"}):
            if n not in local:
                return True
    return False


_BROWSE_TEMPLATE_ENTITY: Dict[str, str] = {
    "loan_extended": "loan",
    "installment_extended": "installment",
    "repayment_extended": "repayment",
    "economic_indicator_extended": "economic_indicator",
    "loan_country_currency_os": "loan",
    "loans_installments_overdue": "loan",
    "loans_all_installments_paid": "loan",
    "loans_missing_condition_mappings": "loan",
    "countries_overdue_balances": "country",
    "countries_without_loans": "country",
    "econ_snapshot_country": "economic_indicator",
    "inflation_compare_europe_region": "economic_indicator",
    "econ_records_high_gdp": "economic_record",
    "econ_inflation_above_threshold": "economic_record",
}


def _infer_browse_entity(plan: NLQueryPlan, nl_question: str) -> str:
    """Fill browse_entity when the planner left it blank."""
    ent = (plan.browse_entity or "").strip().lower()
    if ent:
        return ent
    tmpl = (plan.browse_template or "").strip()
    if tmpl in _BROWSE_TEMPLATE_ENTITY:
        return _BROWSE_TEMPLATE_ENTITY[tmpl]
    q = (nl_question or "").lower()
    if re.search(r"\bloans?\b", q):
        return "loan"
    if re.search(r"\binstallments?\b", q):
        return "installment"
    if re.search(r"\brepayments?\b", q):
        return "repayment"
    if re.search(r"\beconomic\s+indicators?\b", q):
        return "economic_indicator"
    if re.search(r"\bcountr(?:y|ies)\b", q):
        return "country"
    if re.search(r"\bcurrenc", q):
        return "currency"
    if re.search(r"\btransactions?\b", q):
        return "financial_transaction"
    return ent


def _coerce_browse_plan(plan: NLQueryPlan, nl_question: str) -> NLQueryPlan:
    """Route mis-planned browse queries to join-aware templates before execution."""
    q = (nl_question or "").lower()
    ent = _infer_browse_entity(plan, nl_question)
    if ent and ent != (plan.browse_entity or "").strip().lower():
        plan = plan.model_copy(update={"browse_entity": ent})

    if (plan.browse_template or "").strip() and ent:
        # Template + entity already set — still apply status/loan coercion below when needed.
        pass

    ent = (plan.browse_entity or "").strip().lower()
    if ent == "mapping":
        ent = "loan_condition_mapping"
    filt_fields = {f.field for f in plan.browse_filters}

    if ent == "country":
        if re.search(
            r"overdue\s+installment|installment.*overdue|past[\s\-]due\s+installment",
            q,
        ) or ("status" in filt_fields and "installment" in q):
            return plan.model_copy(
                update={
                    "browse_template": "countries_overdue_balances",
                    "browse_filters": [],
                    "browse_projection": plan.browse_projection
                    or ["country_name", "outstanding_balance", "loan_id"],
                }
            )
        if re.search(
            r"(?:no|without|don't\s+have|do\s+not\s+have|lack(?:ing)?)\s+(?:any\s+)?(?:imf\s+)?loan",
            q,
        ) or ("loan_id" in filt_fields and re.search(r"\bnot\b|\bno\b", q)):
            return plan.model_copy(
                update={
                    "browse_template": "countries_without_loans",
                    "browse_filters": [],
                    "browse_projection": plan.browse_projection
                    or ["country_name", "region", "currency_code"],
                }
            )
        if filt_fields & _RELATED_FIELD_HINTS.get("country", set()):
            if "loan" in q or "installment" in q or "repayment" in q:
                return plan.model_copy(
                    update={
                        "browse_entity": "loan",
                        "browse_template": "loan_extended",
                    }
                )

    if ent == "loan" and (
        not plan.browse_template
        or re.search(r"\b(imf\s+)?loans?\b.*\b(country|program)\b", q)
        or re.search(r"\b(country\s+name|loan\s+program|program\s+name)\b", q)
        or "country_name" in (plan.browse_projection or [])
        or "program_name" in (plan.browse_projection or [])
    ):
        proj = plan.browse_projection or [
            "loan_id", "country_name", "program_name", "loan_amount", "currency_code", "status",
        ]
        return plan.model_copy(
            update={
                "browse_template": "loan_extended",
                "browse_projection": proj,
            }
        )

    if ent == "installment" and re.search(r"\bcountry|countries\b", q):
        return plan.model_copy(update={"browse_template": "installment_extended"})

    if ent == "repayment" and (
        "country_name" in filt_fields or re.search(r"\bcountry|countries\b", q)
    ):
        return plan.model_copy(update={"browse_template": "repayment_extended"})

    if ent == "economic_indicator" and (
        not plan.browse_template
        or "country_name" in filt_fields
        or "country" in q
        or re.search(r"\bcountry\s+names?\b", q)
    ):
        proj = plan.browse_projection or [
            "indicator_id", "country_name", "record_date", "CPI", "GDP", "inflation",
        ]
        return plan.model_copy(
            update={
                "browse_template": "economic_indicator_extended",
                "browse_projection": proj,
            }
        )

    if ent == "loan" and not plan.browse_template:
        return plan.model_copy(
            update={
                "browse_template": "loan_extended",
                "browse_projection": plan.browse_projection or [
                    "loan_id", "country_name", "program_name", "loan_amount", "currency_code", "status",
                ],
            }
        )

    # Status-filtered loan lists (planner often sets template but omits entity)
    if re.search(r"\bloans?\b", q) and re.search(r"\bstatus\b", q) and re.search(
        r"\bcompleted\b|\bactive\b|\bpending\b|\boverdue\b", q
    ):
        status_val = "Completed"
        if "active" in q:
            status_val = "Active"
        elif "pending" in q:
            status_val = "Pending"
        elif "overdue" in q:
            status_val = "Overdue"
        return plan.model_copy(
            update={
                "browse_entity": "loan",
                "browse_template": "loan_extended",
                "browse_filters": plan.browse_filters
                or [FilterSpec(field="status", operator="=", value=status_val)],
                "browse_projection": plan.browse_projection or [
                    "loan_id", "country_name", "program_name", "loan_amount", "status",
                ],
            }
        )

    return plan


def _coerce_aggregate_plan(spec: AnalyticsSpec, nl_question: str) -> AnalyticsSpec:
    """Fix common mis-planned aggregates (loans per program, economic by country)."""
    q = (nl_question or "").lower()

    if re.search(r"\bloans?\b", q) and re.search(
        r"\b(program|each\s+program|per\s+program|imf\s+program)\b", q
    ) and re.search(r"\b(number|count|how\s+many|issued)\b", q):
        return spec.model_copy(
            update={
                "module": "loan",
                "group_by": ["program_name"],
                "metrics": [MetricSpec(field="loan_id", aggregation="count")],
                "sort": None,
                "limit": spec.limit or 50,
            }
        )

    # average CPI by member country (CPI on indicator; country via join)
    if re.search(r"\bcpi\b", q) and re.search(
        r"\b(country|countries|member\s+countr|per\s+countr|by\s+countr)\b", q
    ):
        return spec.model_copy(
            update={
                "module": "economic",
                "group_by": ["country_name"],
                "metrics": [MetricSpec(field="CPI", aggregation="avg")],
                "sort": spec.sort,
                "limit": spec.limit or 50,
                "chart_type": spec.chart_type or "bar",
            }
        )

    # top N countries by inflation (inflation on economic_record + country join)
    if re.search(r"\binflation\b", q) and re.search(r"\bcountr", q):
        m_top = re.search(r"\btop\s+(\d+)\b", q)
        limit = int(m_top.group(1)) if m_top else (spec.limit or 5)
        return spec.model_copy(
            update={
                "module": "economic",
                "group_by": ["country_name"],
                "metrics": [MetricSpec(field="inflation", aggregation="avg")],
                "sort": SortSpec(field="inflation", direction="desc"),
                "limit": min(max(limit, 1), 100),
                "chart_type": "bar",
            }
        )

    return spec


def _remap_cross_module_aggregate(spec: AnalyticsSpec) -> AnalyticsSpec:
    """Use module=country when metrics span loans and economic tables."""
    mod = (spec.module or "").strip().lower()
    if mod == "country":
        return spec

    fields: Set[str] = set()
    for m in spec.metrics:
        fields.add(m.field)
    for f in spec.filters:
        fields.add(f.field)
    fields.update(spec.group_by)
    if spec.sort:
        fields.add(spec.sort.field)

    loan_fields = {
        "loan_amount", "loan_id", "status", "interest_rate", "no_of_installments",
        "program_name", "amount_paid", "outstanding_balance",
    }
    econ_fields = {
        "GDP", "inflation", "CPI", "indicator_id", "record_date",
        "industrial_output", "agricultural_output", "services_output",
        "money_supply", "exchange_rate",
    }
    needs_loan = bool(fields & loan_fields)
    needs_econ = bool(fields & econ_fields)
    wants_country = "country_name" in fields or "region" in fields

    if needs_loan and (needs_econ or mod == "economic"):
        return spec.model_copy(update={"module": "country"})
    if mod == "economic" and needs_loan:
        return spec.model_copy(update={"module": "country"})
    if mod == "loan" and needs_econ:
        return spec.model_copy(update={"module": "country"})
    if wants_country and needs_loan and mod not in ("country",):
        return spec.model_copy(update={"module": "country"})
    return spec


def _browse_summary_line(plan: NLQueryPlan, count: int, headline: Optional[str] = None) -> str:
    ent = (plan.browse_entity or "").replace("_", " ").strip()
    base = headline or (ent.title() if ent else "Results")
    tag = _browse_scope_tag(plan)
    mid = f"{base} — {tag}" if tag else base
    noun = "row" if count == 1 else "rows"
    if count == 0:
        return f"{mid} · no {noun}"
    return f"{mid} · {count} {noun}"


def _infer_browse_chart_axes(
    rows: List[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str], str]:
    """Pick x (label) and y (numeric) column names for browse viz."""
    if not rows:
        return None, None, "table"
    sample = rows[0]

    def _num_ok(v: Any) -> bool:
        return not isinstance(v, bool) and isinstance(v, (int, float, Decimal))

    x_order = ["country_name", "name", "program_name", "currency_code", "region", "loan_id"]
    x_key = next((k for k in x_order if k in sample and sample[k] is not None), None)
    if x_key is None:
        x_key = next(
            (k for k, v in sample.items() if isinstance(v, str) and k not in {"status", "currency_code"}),
            None,
        )

    y_order = ["avg_inflation", "inflation", "GDP", "loan_amount",
               "outstanding_balance", "amount", "amount_due", "amount_paid"]
    y_key = next((k for k in y_order if k in sample and _num_ok(sample[k])), None)
    if y_key is None:
        y_key = next(
            (k for k, v in sample.items() if not k.endswith("_id") and _num_ok(v)),
            None,
        )

    if x_key and y_key:
        return x_key, y_key, "bar"
    return None, None, "table"


# ---------------------------------------------------------------------------
# Special browse handlers (templates)
# ---------------------------------------------------------------------------

def _sb_loan_country_currency_os(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "loan")
    mx_sub = (
        db.query(
            models.Repayment.loan_id.label("lid"),
            func.max(models.Repayment.repayment_no).label("mx_no"),
        )
        .group_by(models.Repayment.loan_id)
        .subquery()
    )
    Rlast = aliased(models.Repayment)
    q = (
        db.query(
            models.Country.name.label("country_name"),
            models.Loan.currency_code,
            func.coalesce(Rlast.outstanding_balance, models.Loan.loan_amount).label("outstanding_balance"),
        )
        .select_from(models.Loan)
        .join(models.Country, models.Country.country_id == models.Loan.country_id)
        .outerjoin(mx_sub, mx_sub.c.lid == models.Loan.loan_id)
        .outerjoin(
            Rlast,
            (Rlast.loan_id == models.Loan.loan_id) & (Rlast.repayment_no == mx_sub.c.mx_no),
        )
    )
    rows_out = [
        {
            "country_name": _serialise(cn),
            "currency": _serialise(ccy),
            "outstanding_balance": _serialise(obs),
        }
        for cn, ccy, obs in q.limit(min(plan.browse_limit, 500)).all()
    ]
    return rows_out, "Loans — country, currency, outstanding balance", (
        f"Outstanding balances for {len(rows_out)} loan(s) (latest repayment or original principal)."
    )


def _sb_txn_jan_march(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "financial_transaction")
    mo = extract("month", models.FinancialTransaction.transaction_date)
    q = (
        db.query(models.FinancialTransaction)
        .filter(mo.between(1, 3))
        .order_by(desc(models.FinancialTransaction.transaction_date))
    )
    cols = plan.browse_projection or ["transaction_date", "transaction_type", "amount", "reference"]
    out: List[Dict[str, Any]] = []
    for r in q.limit(min(plan.browse_limit, 500)).all():
        d = _orm_row_dict(r)
        out.append(_reshape_row_ordered([c for c in cols if c in d], d))
    return out, "Financial transactions — January through March", f"{len(out)} transaction(s) in Q1."


def _sb_txn_debits(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "financial_transaction")
    q = (
        db.query(models.FinancialTransaction)
        .filter(
            or_(
                models.FinancialTransaction.transaction_type.ilike("%debit%"),
                models.FinancialTransaction.transaction_type.ilike("%disbursement%"),
            )
        )
        .order_by(desc(models.FinancialTransaction.transaction_date))
    )
    cols = plan.browse_projection or ["transaction_date", "transaction_type", "amount", "reference"]
    out: List[Dict[str, Any]] = []
    for r in q.limit(min(plan.browse_limit, 500)).all():
        d = _orm_row_dict(r)
        out.append(_reshape_row_ordered([c for c in cols if c in d], d))
    return out, "Ledger debits / outgoing disbursements", f"{len(out)} debit-type transaction(s)."


def _sb_loans_all_installments_paid(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "loan")
    Ins = aliased(models.Installment)
    has_schedule = exists().where(Ins.loan_id == models.Loan.loan_id)
    unpaid = exists().where(
        and_(Ins.loan_id == models.Loan.loan_id, not_(Ins.status.ilike("%paid%")))
    )
    q = (
        db.query(models.Loan, models.Country.name.label("country_name"))
        .join(models.Country, models.Country.country_id == models.Loan.country_id)
        .filter(has_schedule)
        .filter(not_(unpaid))
    )
    cols = plan.browse_projection or ["loan_id", "country_name", "loan_amount", "currency_code", "status"]
    out: List[Dict[str, Any]] = []
    for loan, cname in q.limit(min(plan.browse_limit, 500)).all():
        merged = _orm_row_dict(loan)
        merged["country_name"] = _serialise(cname)
        out.append(_reshape_row_ordered([c for c in cols if c in merged], merged))
    return out, "Loans with fully paid installments", f"{len(out)} loan(s) with every installment settled."


def _sb_loans_missing_mappings(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "loan")
    Mp = aliased(models.LoanConditionMapping)
    has_any = exists().where(Mp.loan_id == models.Loan.loan_id)
    q = (
        db.query(models.Loan, models.Country.name.label("country_name"))
        .join(models.Country, models.Country.country_id == models.Loan.country_id)
        .filter(not_(has_any))
    )
    cols = plan.browse_projection or ["loan_id", "country_name", "currency_code", "loan_amount"]
    out: List[Dict[str, Any]] = []
    for loan, cname in q.limit(min(plan.browse_limit, 500)).all():
        merged = _orm_row_dict(loan)
        merged["country_name"] = _serialise(cname)
        out.append(_reshape_row_ordered([c for c in cols if c in merged], merged))
    return out, "Loans lacking condition mappings", f"{len(out)} loan(s) have no condition mappings."


def _sb_loans_overdue_schedule(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "loan")
    Ins = aliased(models.Installment)
    today = date.today()
    overdue = exists().where(
        and_(
            Ins.loan_id == models.Loan.loan_id,
            Ins.due_date < today,
            not_(Ins.status.ilike("%paid%")),
        )
    )
    q = (
        db.query(models.Loan.loan_id, models.Country.name.label("country_name"))
        .join(models.Country, models.Country.country_id == models.Loan.country_id)
        .filter(overdue)
        .distinct()
    )
    cols = plan.browse_projection or ["loan_id", "country_name"]
    rows = [
        _reshape_row_ordered(cols, {"loan_id": _serialise(a), "country_name": _serialise(b)})
        for a, b in q.limit(min(plan.browse_limit, 500)).all()
    ]
    return rows, "Loans with overdue installments", f"{len(rows)} loan(s) carry at least one past-due unpaid installment."


def _sb_installments_partial(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "installment")
    q = (
        db.query(models.Installment)
        .filter(
            or_(
                models.Installment.status.ilike("%partial%"),
                and_(
                    models.Installment.amount_paid.isnot(None),
                    models.Installment.amount_due.isnot(None),
                    models.Installment.amount_paid > 0,
                    models.Installment.amount_paid < models.Installment.amount_due,
                ),
            )
        )
        .order_by(models.Installment.loan_id, models.Installment.installment_no)
    )
    cols = plan.browse_projection or [
        "loan_id", "installment_no", "due_date", "amount_due", "amount_paid", "status",
    ]
    out: List[Dict[str, Any]] = []
    for r in q.limit(min(plan.browse_limit, 500)).all():
        d = _orm_row_dict(r)
        out.append(_reshape_row_ordered([c for c in cols if c in d], d))
    return out, "Partially settled installments", f"{len(out)} installment(s) still short of amount due."


def _sb_loan_mapped_conditions_sheet(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "loan_condition_mapping")
    lid = plan.browse_context.get("loan_id")
    if lid is None:
        for f in plan.browse_filters:
            if str(f.field) == "loan_id":
                op = llm_svc._canonical_filter_op(f.operator).strip()
                if op == "=":
                    try:
                        lid = int(f.value)
                        break
                    except (TypeError, ValueError):
                        continue
    if lid is None:
        raise HTTPException(400, detail="loan_id required in browse_context or filters.")
    lid = int(lid)
    q = (
        db.query(
            models.LoanConditionMapping.loan_id,
            models.LoanCondition.condition_id,
            models.LoanCondition.condition_type,
            models.LoanCondition.description,
            models.LoanCondition.threshold_value,
            models.LoanCondition.eligibility_criteria,
        )
        .join(models.LoanCondition, models.LoanCondition.condition_id == models.LoanConditionMapping.condition_id)
        .filter(models.LoanConditionMapping.loan_id == lid)
        .order_by(models.LoanCondition.condition_id)
    )
    cols = plan.browse_projection or [
        "loan_id", "condition_id", "condition_type", "description",
        "threshold_value", "eligibility_criteria",
    ]
    rows_out: List[Dict[str, Any]] = []
    for m_lid, cid, ctype, descr, thresh, elig in q.limit(min(plan.browse_limit, 500)).all():
        row = {
            "loan_id": _serialise(m_lid),
            "condition_id": _serialise(cid),
            "condition_type": _serialise(ctype),
            "description": _serialise(descr),
            "threshold_value": _serialise(thresh),
            "eligibility_criteria": _serialise(elig),
        }
        rows_out.append(_reshape_row_ordered([c for c in cols if c in row], row))
    ttl = f"Conditions linked to loan #{lid}"
    msg = ttl if rows_out else f"No condition mappings stored for loan #{lid}."
    return rows_out, ttl, msg


def _sb_sum_repaid_for_loan(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "repayment")
    lid = plan.browse_context.get("loan_id")
    if lid is None:
        for flt in plan.browse_filters:
            if flt.field == "loan_id" and flt.operator == "=":
                lid = int(flt.value)
                break
    if lid is None:
        raise HTTPException(400, detail="loan_id required for repayment total.")
    lid = int(lid)
    total = (
        db.query(func.coalesce(func.sum(models.Repayment.amount_paid), 0))
        .filter(models.Repayment.loan_id == lid)
        .scalar()
    )
    total_f = float(_serialise(total))
    row = {"loan_id": lid, "total_amount_paid": total_f}
    cols = plan.browse_projection or ["loan_id", "total_amount_paid"]
    return (
        [_reshape_row_ordered([c for c in cols if c in row], row)],
        "Total repaid toward loan",
        f"Cumulative amount repaid for loan #{lid} is {total_f}.",
    )


def _sb_fx_latest_pair(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "exchange_rate")
    fcur = str(plan.browse_context.get("from_currency", "USD")).strip().upper()
    tcur = str(plan.browse_context.get("to_currency", "EUR")).strip().upper()
    hit = (
        db.query(models.ExchangeRate)
        .filter(models.ExchangeRate.from_currency == fcur, models.ExchangeRate.to_currency == tcur)
        .order_by(desc(models.ExchangeRate.rate_date), desc(models.ExchangeRate.exchange_rate_id))
        .first()
    )
    cols = plan.browse_projection or ["rate_date", "from_currency", "to_currency", "rate"]
    if hit is None:
        return [], f"Latest {fcur}→{tcur}", f"No FX pair stored for {fcur} → {tcur}."
    d = _orm_row_dict(hit)
    return (
        [_reshape_row_ordered([c for c in cols if c in d], d)],
        f"Spot rate {fcur} → {tcur}",
        f"Latest {fcur}→{tcur}: rate {_serialise(hit.rate)} on {_serialise(hit.rate_date)}.",
    )


def _sb_econ_records_gdp_above(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "economic_record")
    floor = Decimal(str(plan.browse_context.get("gdp_above", 500)))
    q = (
        db.query(
            models.EconomicRecord,
            models.Country.name.label("country_name"),
            models.EconomicIndicator.record_date,
        )
        .join(models.EconomicIndicator, models.EconomicRecord.indicator_id == models.EconomicIndicator.indicator_id)
        .join(models.Country, models.EconomicIndicator.country_id == models.Country.country_id)
        .filter(models.EconomicRecord.GDP > floor)
        .order_by(desc(models.EconomicRecord.GDP))
    )
    cols = plan.browse_projection or ["country_name", "record_date", "GDP", "inflation"]
    rows: List[Dict[str, Any]] = []
    for rec, cname, rdate in q.limit(min(plan.browse_limit, 500)).all():
        merged = {
            "country_name": _serialise(cname),
            "record_date": _serialise(rdate),
            "GDP": _serialise(rec.GDP),
            "inflation": _serialise(rec.inflation),
        }
        rows.append(_reshape_row_ordered([c for c in cols if c in merged], merged))
    return rows, f"Economic snapshots — GDP above {floor}", (
        f"{len(rows)} snapshot(s) with GDP exceeding {floor}." if rows
        else f"No snapshots with GDP above {floor}."
    )


def _sb_econ_inflation_above(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "economic_record")
    floor = plan.browse_context.get("inflation_above")
    if floor is None:
        for f in plan.browse_filters:
            if str(f.field).lower() == "inflation" and f.operator in {">", ">="}:
                try:
                    floor = float(f.value)
                    break
                except (TypeError, ValueError):
                    pass
    thresh = Decimal(str(floor if floor is not None else 10))
    q = (
        db.query(
            models.EconomicRecord,
            models.Country.name.label("country_name"),
            models.EconomicIndicator.record_date,
        )
        .join(models.EconomicIndicator, models.EconomicRecord.indicator_id == models.EconomicIndicator.indicator_id)
        .join(models.Country, models.EconomicIndicator.country_id == models.Country.country_id)
        .filter(models.EconomicRecord.inflation > thresh)
        .order_by(desc(models.EconomicRecord.inflation))
    )
    cols = plan.browse_projection or ["country_name", "record_date", "GDP", "inflation"]
    rows_out: List[Dict[str, Any]] = []
    for rec, cname, rdate in q.limit(min(plan.browse_limit, 500)).all():
        merged = {
            "country_name": _serialise(cname),
            "record_date": _serialise(rdate),
            "GDP": _serialise(rec.GDP),
            "inflation": _serialise(rec.inflation),
        }
        rows_out.append(_reshape_row_ordered([c for c in cols if c in merged], merged))
    return rows_out, f"Countries with inflation above {thresh}", (
        f"{len(rows_out)} snapshot(s) with inflation exceeding {thresh}." if rows_out
        else f"No stored rows beat the {thresh} inflation threshold."
    )


def _sb_econ_snapshot_country(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "economic_indicator")
    nm = str(plan.browse_context.get("country") or "").strip()
    if not nm:
        raise HTTPException(400, detail="browse_context.country is required.")
    ctr = db.query(models.Country).filter(models.Country.name.ilike(f"%{nm}%")).first()
    if ctr is None:
        return [], "Economic indicators", f"No country named like '{nm}'."
    ind = (
        db.query(models.EconomicIndicator)
        .filter(models.EconomicIndicator.country_id == ctr.country_id)
        .order_by(desc(models.EconomicIndicator.record_date), desc(models.EconomicIndicator.indicator_id))
        .first()
    )
    if ind is None:
        return [], "Economic indicators", f"No indicators stored for {ctr.name}."
    rec = db.query(models.EconomicRecord).filter(models.EconomicRecord.indicator_id == ind.indicator_id).first()
    merged: Dict[str, Any] = {
        "country_name": ctr.name,
        "record_date": _serialise(ind.record_date),
        "CPI": _serialise(ind.CPI),
        "exchange_rate": _serialise(ind.exchange_rate),
        "interest_rate": _serialise(ind.interest_rate),
    }
    if rec is not None:
        merged["GDP"] = _serialise(rec.GDP)
        merged["inflation"] = _serialise(rec.inflation)

    cols = plan.browse_projection or [
        "country_name", "record_date", "CPI", "exchange_rate",
        "interest_rate", "GDP", "inflation",
    ]
    snippet = []
    if rec and rec.GDP is not None:
        snippet.append(f"GDP ~{_serialise(rec.GDP)}")
    if rec and rec.inflation is not None:
        snippet.append(f"inflation ~{_serialise(rec.inflation)}")
    if ind.CPI is not None:
        snippet.append(f"CPI {_serialise(ind.CPI)}")
    summary_line = (
        f"Latest indicators for {ctr.name} (as of {_serialise(ind.record_date)}): "
        + ", ".join(snippet) + "." if snippet else f"Indicators on record for {ctr.name}."
    )
    return (
        [_reshape_row_ordered([c for c in cols if c in merged], merged)],
        f"Indicators — {ctr.name}",
        summary_line,
    )


def _sb_inflation_compare_europe(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    """
    European inflation comparison — country list comes 100% from the DB
    by pattern-matching `country.region`; no country names are hardcoded.
    """
    _rbac_can_browse_entity(role, "economic_indicator")

    # Resolve European region labels dynamically
    europe_regions = _distinct_region_labels_matching(db, "europe")
    if europe_regions:
        geo = models.Country.region.in_(europe_regions)
    else:
        geo = func.lower(models.Country.region).like("%europe%")

    avg_infl = func.avg(models.EconomicRecord.inflation).label("avg_inflation")
    max_dt = func.max(models.EconomicIndicator.record_date).label("record_date")

    q = (
        db.query(models.Country.name.label("country_name"), avg_infl, max_dt)
        .join(models.EconomicIndicator, models.EconomicIndicator.country_id == models.Country.country_id)
        .join(models.EconomicRecord, models.EconomicRecord.indicator_id == models.EconomicIndicator.indicator_id)
        .filter(geo)
        .filter(models.Country.region.isnot(None))
        .group_by(models.Country.name)
        .order_by(desc(avg_infl))
    )

    cols = plan.browse_projection or ["country_name", "avg_inflation", "record_date"]
    rows: List[Dict[str, Any]] = []
    vals: List[Tuple[str, float]] = []
    for cname, infl_avg, dt in q.limit(min(plan.browse_limit, 500)).all():
        merged = {
            "country_name": _serialise(cname),
            "avg_inflation": _serialise(infl_avg),
            "record_date": _serialise(dt),
        }
        rows.append(_reshape_row_ordered([c for c in cols if c in merged], merged))
        try:
            vals.append((str(cname), float(infl_avg)))
        except (TypeError, ValueError):
            pass

    headline = ""
    if vals:
        top = max(vals, key=lambda x: x[1])
        bot = min(vals, key=lambda x: x[1])
        headline = (
            f"Among {len(rows)} European economies: highest avg inflation is {top[0]} "
            f"(~{top[1]:.2f}), lowest is {bot[0]} (~{bot[1]:.2f})."
        )
    return rows, "European inflation — average per country", headline


def _sb_countries_overdue_balances(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "country")
    Ins = aliased(models.Installment)
    today = date.today()
    mx_sub = (
        db.query(
            models.Repayment.loan_id.label("lid"),
            func.max(models.Repayment.repayment_no).label("mx_no"),
        )
        .group_by(models.Repayment.loan_id)
        .subquery()
    )
    Rlast = aliased(models.Repayment)
    overdue_loan = exists().where(
        and_(
            Ins.loan_id == models.Loan.loan_id,
            Ins.due_date < today,
            not_(Ins.status.ilike("%paid%")),
        )
    )
    q = (
        db.query(
            models.Country.name.label("country_name"),
            models.Loan.loan_id,
            func.coalesce(Rlast.outstanding_balance, models.Loan.loan_amount).label(
                "outstanding_balance"
            ),
        )
        .select_from(models.Country)
        .join(models.Loan, models.Loan.country_id == models.Country.country_id)
        .filter(overdue_loan)
        .outerjoin(mx_sub, mx_sub.c.lid == models.Loan.loan_id)
        .outerjoin(
            Rlast,
            (Rlast.loan_id == models.Loan.loan_id) & (Rlast.repayment_no == mx_sub.c.mx_no),
        )
        .distinct()
    )
    cols = plan.browse_projection or ["country_name", "loan_id", "outstanding_balance"]
    rows_out = [
        _reshape_row_ordered(
            cols,
            {
                "country_name": _serialise(cname),
                "loan_id": _serialise(lid),
                "outstanding_balance": _serialise(os_bal),
            },
        )
        for cname, lid, os_bal in q.limit(min(plan.browse_limit, 500)).all()
    ]
    title = "Countries with overdue installments"
    summary = (
        f"{len(rows_out)} country/loan row(s) with past-due installments."
        if rows_out
        else "No countries currently have overdue installments with outstanding balances."
    )
    return rows_out, title, summary


def _sb_countries_without_loans(
    db: Session, role: str, user_id: int, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    _rbac_can_browse_entity(role, "country")
    has_loan = exists().where(models.Loan.country_id == models.Country.country_id)
    q = db.query(models.Country).filter(not_(has_loan))
    for f in plan.browse_filters:
        if hasattr(models.Country, f.field):
            q = _apply_column_filter(q, models.Country, f)
    rows_orm = q.limit(min(plan.browse_limit, 500)).all()
    data = [_orm_row_dict(r) for r in rows_orm]
    for row in data:
        if row.get("name") and not row.get("country_name"):
            row["country_name"] = row["name"]
    if plan.browse_projection:
        data = _apply_browse_projection(data, plan.browse_projection, entity="country")
    title = "Countries without IMF loans"
    return data, title, _browse_summary_line(plan, len(data), headline=title)


def _browse_installment_extended(db: Session, plan: NLQueryPlan) -> List[Dict[str, Any]]:
    q = (
        db.query(
            models.Installment,
            models.Country.name.label("country_name"),
            models.Loan.loan_amount,
            models.Loan.status,
        )
        .join(models.Loan, models.Installment.loan_id == models.Loan.loan_id)
        .join(models.Country, models.Loan.country_id == models.Country.country_id)
    )
    for f in plan.browse_filters:
        if hasattr(models.Installment, f.field):
            q = _apply_column_filter(q, models.Installment, f)
        elif f.field == "country_name":
            op = llm_svc._canonical_filter_op(f.operator).lower()
            if op == "ilike":
                q = q.filter(models.Country.name.ilike(str(f.value)))
            elif op == "=":
                q = q.filter(models.Country.name == str(f.value))
        elif hasattr(models.Loan, f.field):
            q = _apply_column_filter(q, models.Loan, f)
    cols = plan.browse_projection or [
        "loan_id", "installment_no", "country_name", "due_date",
        "amount_due", "amount_paid", "status",
    ]
    rows_out: List[Dict[str, Any]] = []
    for inst, cname, lamt, lstatus in q.limit(min(plan.browse_limit, 500)).all():
        row = _orm_row_dict(inst)
        row["country_name"] = _serialise(cname)
        row["loan_amount"] = _serialise(lamt)
        row["status"] = _serialise(lstatus)
        rows_out.append(_reshape_row_ordered([c for c in cols if c in row], row))
    return rows_out


def _browse_repayment_extended(db: Session, plan: NLQueryPlan) -> List[Dict[str, Any]]:
    q = (
        db.query(
            models.Repayment,
            models.Country.name.label("country_name"),
            models.Loan.loan_amount,
        )
        .join(models.Loan, models.Repayment.loan_id == models.Loan.loan_id)
        .join(models.Country, models.Loan.country_id == models.Country.country_id)
    )
    for f in plan.browse_filters:
        if hasattr(models.Repayment, f.field):
            q = _apply_column_filter(q, models.Repayment, f)
        elif f.field == "country_name":
            op = llm_svc._canonical_filter_op(f.operator).lower()
            if op == "ilike":
                q = q.filter(models.Country.name.ilike(str(f.value)))
            elif op == "=":
                q = q.filter(models.Country.name == str(f.value))
    cols = plan.browse_projection or [
        "loan_id", "repayment_no", "country_name", "amount_paid",
        "payment_date", "outstanding_balance",
    ]
    rows_out: List[Dict[str, Any]] = []
    for rep, cname, lamt in q.limit(min(plan.browse_limit, 500)).all():
        row = _orm_row_dict(rep)
        row["country_name"] = _serialise(cname)
        row["loan_amount"] = _serialise(lamt)
        rows_out.append(_reshape_row_ordered([c for c in cols if c in row], row))
    return rows_out


def _browse_economic_indicator_extended(db: Session, plan: NLQueryPlan) -> List[Dict[str, Any]]:
    q = (
        db.query(
            models.EconomicIndicator,
            models.Country.name.label("country_name"),
            models.EconomicRecord.GDP,
            models.EconomicRecord.inflation,
        )
        .join(models.Country, models.EconomicIndicator.country_id == models.Country.country_id)
        .outerjoin(
            models.EconomicRecord,
            models.EconomicRecord.indicator_id == models.EconomicIndicator.indicator_id,
        )
    )
    for f in plan.browse_filters:
        if hasattr(models.EconomicIndicator, f.field):
            q = _apply_column_filter(q, models.EconomicIndicator, f)
        elif f.field == "country_name":
            op = llm_svc._canonical_filter_op(f.operator).lower()
            if op == "ilike":
                q = q.filter(models.Country.name.ilike(str(f.value)))
            elif op == "=":
                q = q.filter(models.Country.name == str(f.value))
        elif f.field in ("GDP", "inflation"):
            q = _apply_column_filter(q, models.EconomicRecord, f)
    cols = plan.browse_projection or [
        "indicator_id", "country_name", "record_date", "CPI", "GDP", "inflation",
    ]
    rows_out: List[Dict[str, Any]] = []
    for ind, cname, gdp, infl in q.limit(min(plan.browse_limit, 500)).all():
        row = _orm_row_dict(ind)
        row["country_name"] = _serialise(cname)
        row["GDP"] = _serialise(gdp)
        row["inflation"] = _serialise(infl)
        rows_out.append(_reshape_row_ordered([c for c in cols if c in row], row))
    return rows_out


_EXTENDED_BROWSE_HANDLERS = {
    "installment_extended": _browse_installment_extended,
    "repayment_extended": _browse_repayment_extended,
    "economic_indicator_extended": _browse_economic_indicator_extended,
}


# ---------------------------------------------------------------------------
# Special template dispatch table
# ---------------------------------------------------------------------------

_SPECIAL_BROWSE: Dict[
    str, Callable[[Session, str, int, NLQueryPlan], Tuple[List[Dict[str, Any]], str, str]]
] = {
    "countries_overdue_balances": _sb_countries_overdue_balances,
    "countries_without_loans": _sb_countries_without_loans,
    "loan_country_currency_os": _sb_loan_country_currency_os,
    "txn_jan_through_march": _sb_txn_jan_march,
    "txn_debits_outflows": _sb_txn_debits,
    "loans_all_installments_paid": _sb_loans_all_installments_paid,
    "loans_missing_condition_mappings": _sb_loans_missing_mappings,
    "loans_installments_overdue": _sb_loans_overdue_schedule,
    "installments_partial_only": _sb_installments_partial,
    "loan_mapped_conditions_sheet": _sb_loan_mapped_conditions_sheet,
    "scalar_sum_repaid_by_loan": _sb_sum_repaid_for_loan,
    "fx_latest_pair": _sb_fx_latest_pair,
    "econ_records_high_gdp": _sb_econ_records_gdp_above,
    "econ_inflation_above_threshold": _sb_econ_inflation_above,
    "econ_snapshot_country": _sb_econ_snapshot_country,
    "inflation_compare_europe_region": _sb_inflation_compare_europe,
}


# ---------------------------------------------------------------------------
# loan_extended template
# ---------------------------------------------------------------------------

def _browse_template_loan_extended(db: Session, plan: NLQueryPlan) -> List[Dict[str, Any]]:
    limit = min(plan.browse_limit, 500)
    q = (
        db.query(
            models.Loan,
            models.Country.name.label("country_name"),
            models.LoanProgram.program_name.label("program_name"),
        )
        .join(models.Country, models.Loan.country_id == models.Country.country_id, isouter=True)
        .join(models.LoanProgram, models.Loan.program_id == models.LoanProgram.program_id, isouter=True)
    )
    for f in plan.browse_filters:
        if hasattr(models.Loan, f.field):
            if f.field == "status" and llm_svc._canonical_filter_op(f.operator) == "=":
                q = q.filter(models.Loan.status.ilike(str(f.value)))
            else:
                q = _apply_column_filter(q, models.Loan, f)
        elif f.field == "country_name":
            if f.operator.lower() == "ilike":
                q = q.filter(models.Country.name.ilike(str(f.value)))
            elif f.operator == "=":
                q = q.filter(models.Country.name == str(f.value))
            else:
                raise HTTPException(400, detail="Only = or ilike filters on country_name here")
        elif f.field == "program_name":
            op = llm_svc._canonical_filter_op(f.operator).lower()
            if op == "ilike":
                q = q.filter(models.LoanProgram.program_name.ilike(str(f.value)))
            elif op == "=":
                q = q.filter(models.LoanProgram.program_name == str(f.value))

    order_field = (plan.browse_order_field or "").strip()
    if order_field and hasattr(models.Loan, order_field):
        col = getattr(models.Loan, order_field)
        q = q.order_by(desc(col) if (plan.browse_order_dir or "asc").lower() == "desc" else asc(col))

    proj = plan.browse_projection
    default_order = ["loan_id", "country_name", "currency_code", "program_name",
                     "loan_amount", "interest_rate", "status"]
    cols = proj or default_order

    rows_out: List[Dict[str, Any]] = []
    for loan, cname, pname in q.limit(limit).all():
        row = _orm_row_dict(loan)
        row["country_name"] = _serialise(cname)
        row["program_name"] = _serialise(pname)
        rows_out.append(_reshape_row_ordered([c for c in cols if c in row], row))
    return rows_out


# ---------------------------------------------------------------------------
# execute_browse
# ---------------------------------------------------------------------------

def execute_browse(
    db: Session,
    role: str,
    user_id: int,
    plan: NLQueryPlan,
    *,
    nl_question: str = "",
) -> Tuple[List[Dict[str, Any]], str, str]:
    plan = _coerce_browse_plan(plan, nl_question)
    ent = (plan.browse_entity or "").strip().lower()
    if not ent:
        ent = _infer_browse_entity(plan, nl_question)
        if ent:
            plan = plan.model_copy(update={"browse_entity": ent})
    if ent == "mapping":
        ent = "loan_condition_mapping"
    if not ent:
        raise HTTPException(
            status_code=400,
            detail="Could not determine which table to browse. Try: browse_entity=loan with browse_template=loan_extended.",
        )

    tmpl = (plan.browse_template or "").strip()
    ext_handler = _EXTENDED_BROWSE_HANDLERS.get(tmpl)
    if ext_handler is not None:
        browse_ent = ent or _BROWSE_TEMPLATE_ENTITY.get(tmpl, ent)
        if not browse_ent:
            raise HTTPException(status_code=400, detail=f"Unknown browse template '{tmpl}'.")
        if not _entities_for_role(role).issuperset({browse_ent}):
            raise HTTPException(status_code=403, detail=f"Role '{role}' cannot browse '{browse_ent}'.")
        ent = browse_ent
        rows = ext_handler(db, plan)
        title = ent.replace("_", " ").title() + " (joined)"
        return rows, title, _browse_summary_line(plan, len(rows))
    if tmpl in _SPECIAL_BROWSE:
        rows, title, summary = _SPECIAL_BROWSE[tmpl](db, role, user_id, plan)
        return rows, title, summary

    if not _entities_for_role(role).issuperset({ent}):
        raise HTTPException(status_code=403, detail=f"Role '{role}' cannot browse '{ent}'.")

    if tmpl == "loan_extended":
        rows = _browse_template_loan_extended(db, plan)
        title = "Loans — country & program context"
        return rows, title, _browse_summary_line(plan, len(rows), headline="Loans")

    model = ENTITY_MODELS.get(ent)
    if not model:
        raise HTTPException(400, detail=f"Unknown browse entity '{ent}'")

    if _browse_needs_join(ent, plan):
        tmpl_auto = {
            "installment": "installment_extended",
            "repayment": "repayment_extended",
            "economic_indicator": "economic_indicator_extended",
        }.get(ent)
        if tmpl_auto and tmpl_auto in _EXTENDED_BROWSE_HANDLERS:
            rows = _EXTENDED_BROWSE_HANDLERS[tmpl_auto](db, plan)
            title = ent.replace("_", " ").title() + " (joined)"
            return rows, title, _browse_summary_line(plan, len(rows))

    q = db.query(model)
    for f in plan.browse_filters:
        if not hasattr(model, f.field):
            raise HTTPException(
                400,
                detail=(
                    f"Field '{f.field}' not on '{ent}'. "
                    "Try browse_template loan_extended or a country-level template for cross-table filters."
                ),
            )
        q = _apply_column_filter(q, model, f)

    if ent == "audit_log" and role != "admin":
        q = q.filter(models.AuditLog.user_id == user_id)

    order_field = (plan.browse_order_field or "").strip()
    if order_field and hasattr(model, order_field):
        col = getattr(model, order_field)
        q = q.order_by(
            desc(col) if (plan.browse_order_dir or "asc").lower() == "desc" else asc(col)
        )

    rows_orm = q.limit(min(plan.browse_limit, 500)).all()
    hide = _HIDDEN_USER_COLS if ent == "users" else set()
    data = [_orm_row_dict(r, hide) for r in rows_orm]

    # Expose `name` as `country_name` for country entity
    if ent == "country":
        for row in data:
            if row.get("name") is not None and not row.get("country_name"):
                row["country_name"] = row["name"]

    if plan.browse_projection:
        data = _apply_browse_projection(data, plan.browse_projection, entity=ent)

    title = ent.replace("_", " ").title()
    if plan.browse_filters:
        title += " — filtered"

    return data, title, _browse_summary_line(plan, len(data))


# ---------------------------------------------------------------------------
# execute_mutate
# ---------------------------------------------------------------------------

def _require_admin_nl(role: str) -> None:
    if (role or "").lower() != "admin":
        raise HTTPException(status_code=403, detail=ADMIN_ASSISTANT_ONLY)


def execute_mutate(
    db: Session,
    user_id: int,
    role: str,
    plan: NLQueryPlan,
    *,
    nl_question: str = "",
) -> Tuple[List[Dict[str, Any]], str, str]:
    from app.services.nl_mutate_service import (
        guard_whole_table_delete,
        resolve_mutate_keys,
        validate_create_fields,
    )

    _require_admin_nl(role)
    entity = (plan.mutate_entity or "").strip().lower()
    if entity == "mapping":
        entity = "loan_condition_mapping"
    if entity == "indicator":
        entity = "economic_indicator"

    op = (plan.mutate_op or "").strip().lower()
    body = dict(plan.mutate_body or {})
    keys = dict(plan.mutate_keys or {})

    guard_whole_table_delete(nl_question, keys, op)
    keys = resolve_mutate_keys(db, entity, op, keys, body)

    if op == "create":
        validate_create_fields(entity, body)

    def audit(msg: str, ent: str) -> None:
        write_audit_log(db, user_id, f"NL {msg}", ent)

    # ── currency ──────────────────────────────────────────────────────────
    if entity == "currency":
        code = keys.get("currency_code") or body.pop("currency_code", None)
        if op == "create":
            payload = schemas.CurrencyCreate(**{**body, "currency_code": str(code).upper()})
            obj = crud_loans.create_currency(db, payload)
            audit(f"currency create {payload.currency_code}", "Currency")
            return [_orm_row_dict(obj)], "Currency", f"Added currency {obj.currency_code}"
        if op == "update":
            if not code:
                raise HTTPException(
                    status_code=400,
                    detail="Currency update requires the existing currency name or code (e.g. Indian Rupee or IND).",
                )
            cc = str(code).upper()
            new_code = body.pop("new_currency_code", None) or body.pop("currency_code_new", None)
            if new_code is None:
                for k in list(body.keys()):
                    if k in ("currency_code", "new_code") and body[k]:
                        new_code = body.pop(k)
                        break
            patch = {
                k: body.get(k)
                for k in ("currency_name", "symbol", "exchange_regime")
                if body.get(k) is not None
            }
            if new_code and str(new_code).upper() != cc:
                obj = crud_loans.rename_currency_code(
                    db,
                    cc,
                    str(new_code).upper(),
                    currency_name=patch.get("currency_name"),
                    symbol=patch.get("symbol"),
                    exchange_regime=patch.get("exchange_regime"),
                )
                if not obj:
                    raise HTTPException(404, detail="Currency not found")
                audit(f"currency rename {cc} -> {obj.currency_code}", "Currency")
                return [_orm_row_dict(obj)], "Currency", f"Renamed currency {cc} → {obj.currency_code}"
            if not patch:
                raise HTTPException(
                    status_code=400,
                    detail="Currency update requires currency_name, symbol, exchange_regime, or a new currency code.",
                )
            obj = crud_loans.update_currency_patch(db, cc, **patch)
            if not obj:
                raise HTTPException(404, detail="Currency not found")
            audit(f"currency update {cc}", "Currency")
            return [_orm_row_dict(obj)], "Currency", f"Updated currency {cc}"
        if op == "delete":
            cc = str(code).upper()
            crud_loans.delete_currency(db, cc)
            audit(f"currency delete {cc}", "Currency")
            return [{"currency_code": cc}], "Currency", f"Deleted currency {cc}"

    # ── country ───────────────────────────────────────────────────────────
    if entity == "country":
        if op == "create":
            obj = crud_loans.create_country(db, schemas.CountryCreate(**body))
            audit(f"country create id={obj.country_id}", "Country")
            return [_orm_row_dict(obj)], "Country", f"Added country {obj.name}"
        if op == "update":
            cid = int(keys["country_id"])
            existing = crud_loans.get_country(db, cid)
            if not existing:
                raise HTTPException(404, "Country not found")
            merged = {
                "currency_code": existing.currency_code,
                "name": existing.name,
                "region": existing.region,
                "population": existing.population,
            }
            merged.update({k: v for k, v in body.items() if v is not None})
            obj = crud_loans.update_country(db, cid, schemas.CountryCreate(**merged))
            audit(f"country update id={cid}", "Country")
            return [_orm_row_dict(obj)], "Country", f"Updated country #{cid}"
        if op == "delete":
            cid = int(keys["country_id"])
            crud_loans.delete_country(db, cid)
            audit(f"country delete id={cid}", "Country")
            return [{"country_id": cid}], "Country", f"Removed country #{cid}"

    # ── loan_program ──────────────────────────────────────────────────────
    if entity == "loan_program":
        if op == "create":
            obj = crud_loans.create_loan_program(db, schemas.LoanProgramCreate(**body))
            audit(f"program create id={obj.program_id}", "LoanProgram")
            return [_orm_row_dict(obj)], "Loan program", f"Added program {obj.program_name}"
        if op == "update":
            pid = int(keys["program_id"])
            obj = crud_loans.update_loan_program_patch(db, pid, body)
            if not obj:
                raise HTTPException(404, "Loan program not found")
            audit(f"program patch id={pid}", "LoanProgram")
            return [_orm_row_dict(obj)], "Loan program", f"Updated program #{pid}"
        if op == "delete":
            pid = int(keys["program_id"])
            crud_loans.delete_loan_program(db, pid)
            audit(f"program delete id={pid}", "LoanProgram")
            return [{"program_id": pid}], "Loan program", f"Deleted program #{pid}"

    # ── imf_account ───────────────────────────────────────────────────────
    if entity == "imf_account":
        if op == "create":
            obj = crud_loans.create_imf_account(db, schemas.IMFAccountCreate(**body))
            audit(f"imf account create id={obj.imf_account_id}", "IMFAccount")
            return [_orm_row_dict(obj)], "IMF account", f"Added IMF account #{obj.imf_account_id}"
        if op == "delete":
            aid = int(keys["imf_account_id"])
            crud_loans.delete_imf_account(db, aid)
            audit(f"imf account delete id={aid}", "IMFAccount")
            return [{"imf_account_id": aid}], "IMF account", f"Deleted IMF account #{aid}"

    # ── users / roles ─────────────────────────────────────────────────────
    if entity == "users":
        if op == "create":
            obj = crud_users.create_user(db, schemas.UserCreate(**body))
            audit(f"user create id={obj.user_id}", "Users")
            return [_orm_row_dict(obj, _HIDDEN_USER_COLS)], "User", f"Added user {obj.email}"
        if op == "update":
            uid = int(keys["user_id"])
            if not body:
                raise HTTPException(400, detail="Update requires at least one field to change (e.g. name, email).")
            obj = crud_users.update_user(db, uid, schemas.UserUpdate(**body))
            if not obj:
                raise HTTPException(404, "User not found")
            audit(f"user update id={uid}", "Users")
            new_name = body.get("name") or obj.name
            return [_orm_row_dict(obj, _HIDDEN_USER_COLS)], "User", f"Updated user #{uid} ({new_name})"
        if op == "delete":
            uid = int(keys["user_id"])
            crud_users.delete_user(db, uid)
            audit(f"user delete id={uid}", "Users")
            return [{"user_id": uid}], "User", f"Deleted user #{uid}"

    if entity == "admin" and op == "create":
        obj = crud_users.create_admin(db, schemas.AdminCreate(**body))
        audit(f"assign admin user_id={obj.user_id}", "Admin")
        return [_orm_row_dict(obj)], "Admin role", f"Granted admin to user #{obj.user_id}"

    if entity == "officer" and op == "create":
        obj = crud_users.create_officer(db, schemas.OfficerCreate(**body))
        audit(f"assign officer user_id={obj.user_id}", "Officer")
        return [_orm_row_dict(obj)], "Officer role", f"Granted officer to user #{obj.user_id}"

    if entity == "economicanalyst" and op == "create":
        obj = crud_users.create_analyst(db, schemas.EconomicAnalystCreate(**body))
        audit(f"assign analyst user_id={obj.user_id}", "EconomicAnalyst")
        return [_orm_row_dict(obj)], "Analyst role", f"Granted analyst to user #{obj.user_id}"

    # ── loan ──────────────────────────────────────────────────────────────
    if entity == "loan":
        if op == "create":
            if "country_name" in body and "country_id" not in body:
                nm = str(body.pop("country_name")).strip()
                hit = db.query(models.Country).filter(models.Country.name.ilike(nm)).first()
                if not hit:
                    raise HTTPException(400, detail=f"Country '{nm}' not found")
                body["country_id"] = hit.country_id
            obj = crud_loans.create_loan(db, schemas.LoanCreate(**body))
            audit(f"loan create id={obj.loan_id}", "Loan")
            return [_orm_row_dict(obj)], "Loan", f"Created loan #{obj.loan_id}"
        if op == "update":
            lid = keys.get("loan_id")
            if lid is None:
                m = re.search(r"\bloan\s*id\s*=\s*(\d+)", nl_question or "", re.I)
                if m:
                    lid = int(m.group(1))
                elif body.get("loan_id") is not None:
                    lid = int(body.pop("loan_id"))
            if lid is None:
                raise HTTPException(400, detail="Loan update requires loan_id in mutate_keys or body.")
            lid = int(lid)
            patch_body = dict(body)
            if "no_of_installments" in patch_body:
                patch_body["no_of_installments"] = int(patch_body["no_of_installments"])
            obj = crud_loans.update_loan(db, lid, schemas.LoanUpdate(**patch_body))
            if not obj:
                raise HTTPException(404, "Loan not found")
            audit(f"loan patch id={lid}", "Loan")
            return [_orm_row_dict(obj)], "Loan", f"Updated loan #{lid}"
        if op == "delete":
            lid = int(keys["loan_id"])
            crud_loans.delete_loan(db, lid)
            audit(f"loan delete id={lid}", "Loan")
            return [{"loan_id": lid}], "Loan", f"Deleted loan #{lid}"

    # ── loan_condition & mapping ──────────────────────────────────────────
    if entity == "loan_condition":
        if op == "create":
            obj = crud_loans.create_loan_condition(db, schemas.LoanConditionCreate(**body))
            audit(f"condition create id={obj.condition_id}", "LoanCondition")
            return [_orm_row_dict(obj)], "Loan condition", f"Added condition #{obj.condition_id}"
        if op == "delete":
            cid = int(keys["condition_id"])
            crud_loans.delete_loan_condition(db, cid)
            audit(f"condition delete id={cid}", "LoanCondition")
            return [{"condition_id": cid}], "Loan condition", f"Deleted condition #{cid}"

    if entity == "loan_condition_mapping":
        if op == "create":
            obj = crud_loans.create_mapping(db, schemas.LoanConditionMappingCreate(**body))
            audit(f"mapping create loan={body.get('loan_id')}", "Mapping")
            return [{"loan_id": obj.loan_id, "condition_id": obj.condition_id}], "Mapping", "Linked condition to loan"
        if op == "delete":
            crud_loans.delete_mapping(db, int(keys["loan_id"]), int(keys["condition_id"]))
            audit("mapping delete", "Mapping")
            return [keys], "Mapping", "Removed condition link"

    # ── economic / fx ─────────────────────────────────────────────────────
    if entity == "economic_indicator":
        if op == "create":
            obj = crud_econ.create_indicator(db, schemas.EconomicIndicatorCreate(**body))
            audit(f"indicator create id={obj.indicator_id}", "EconomicIndicator")
            return [_orm_row_dict(obj)], "Indicator", f"Added indicator #{obj.indicator_id}"
        if op == "update":
            iid = int(keys["indicator_id"])
            obj = crud_econ.update_indicator(db, iid, schemas.EconomicIndicatorCreate(**body))
            if not obj:
                raise HTTPException(404, "Indicator not found")
            audit(f"indicator update id={iid}", "EconomicIndicator")
            return [_orm_row_dict(obj)], "Indicator", f"Updated indicator #{iid}"
        if op == "delete":
            iid = int(keys["indicator_id"])
            crud_econ.delete_indicator(db, iid)
            audit(f"indicator delete id={iid}", "EconomicIndicator")
            return [{"indicator_id": iid}], "Indicator", f"Deleted indicator #{iid}"

    if entity == "economic_record":
        if op == "create":
            if "country_name" in body and "indicator_id" not in body:
                nm = str(body.pop("country_name")).strip()
                ctr = db.query(models.Country).filter(models.Country.name.ilike(f"%{nm}%")).first()
                if not ctr:
                    raise HTTPException(404, detail=f"No country found matching '{nm}'.")
                _ind, rec = crud_econ.get_latest_record_for_country(db, ctr.country_id)
                if _ind and "indicator_id" not in body:
                    body["indicator_id"] = _ind.indicator_id
            obj = crud_econ.create_record(db, schemas.EconomicRecordCreate(**body))
            audit(f"record create id={obj.record_id}", "EconomicRecord")
            return [_orm_row_dict(obj)], "Economic record", f"Added record #{obj.record_id}"
        if op == "update":
            rid = keys.get("record_id")
            if rid is None:
                lookup = (
                    keys.pop("lookup_name", None)
                    or keys.pop("name", None)
                    or body.pop("lookup_name", None)
                    or body.pop("country_name", None)
                )
                if lookup:
                    ctr = (
                        db.query(models.Country)
                        .filter(models.Country.name.ilike(f"%{str(lookup).strip()}%"))
                        .first()
                    )
                    if not ctr:
                        raise HTTPException(404, detail=f"No country found matching '{lookup}'.")
                    _ind, rec = crud_econ.get_latest_record_for_country(db, ctr.country_id)
                    if not rec:
                        raise HTTPException(
                            404,
                            detail=f"No economic record found for country '{ctr.name}'.",
                        )
                    rid = rec.record_id
            if rid is None:
                raise HTTPException(
                    400,
                    detail="Economic record update requires record_id or country name in mutate_keys.",
                )
            patch = {k: body[k] for k in ("GDP", "inflation") if k in body and body[k] is not None}
            if not patch:
                raise HTTPException(400, detail="Update requires GDP and/or inflation in mutate_body.")
            obj = crud_econ.update_record(db, int(rid), patch)
            if not obj:
                raise HTTPException(404, detail="Economic record not found")
            audit(f"record update id={rid}", "EconomicRecord")
            return [_orm_row_dict(obj)], "Economic record", f"Updated economic record #{rid}"
        if op == "delete":
            rid = int(keys["record_id"])
            crud_econ.delete_record(db, rid)
            audit(f"record delete id={rid}", "EconomicRecord")
            return [{"record_id": rid}], "Economic record", f"Deleted record #{rid}"

    if entity == "exchange_rate":
        if op == "create":
            obj = crud_econ.create_exchange_rate(db, schemas.ExchangeRateCreate(**body))
            audit(f"FX create id={obj.exchange_rate_id}", "ExchangeRate")
            return [_orm_row_dict(obj)], "Exchange rate", f"Added FX row #{obj.exchange_rate_id}"
        if op == "update":
            rid = int(keys["exchange_rate_id"])
            obj = crud_econ.update_exchange_rate_patch(db, rid, body)
            if not obj:
                raise HTTPException(404, detail="Exchange rate not found")
            audit(f"FX update id={rid}", "ExchangeRate")
            return [_orm_row_dict(obj)], "Exchange rate", f"Updated FX #{rid}"
        if op == "delete":
            rid = int(keys["exchange_rate_id"])
            crud_econ.delete_exchange_rate(db, rid)
            audit(f"FX delete id={rid}", "ExchangeRate")
            return [{"exchange_rate_id": rid}], "Exchange rate", f"Removed FX #{rid}"

    if entity == "imf_account":
        if op == "update":
            aid = int(keys["imf_account_id"])
            obj = crud_loans.update_imf_account_patch(db, aid, body)
            if not obj:
                raise HTTPException(404, detail="IMF account not found")
            audit(f"imf account update id={aid}", "IMFAccount")
            return [_orm_row_dict(obj)], "IMF account", f"Updated IMF account #{aid}"

    if entity == "loan_condition":
        if op == "update":
            cid = int(keys["condition_id"])
            obj = crud_loans.update_loan_condition_patch(db, cid, body)
            if not obj:
                raise HTTPException(404, detail="Loan condition not found")
            audit(f"condition update id={cid}", "LoanCondition")
            return [_orm_row_dict(obj)], "Loan condition", f"Updated condition #{cid}"

    if entity == "loan_disbursement":
        if op == "update":
            lid = int(keys["loan_id"])
            dno = int(keys["disbursement_no"])
            obj = crud_loans.update_disbursement_patch(db, lid, dno, body)
            if not obj:
                raise HTTPException(404, detail="Disbursement not found")
            audit(f"disbursement update loan={lid} no={dno}", "LoanDisbursement")
            return [_orm_row_dict(obj)], "Disbursement", f"Updated disbursement #{dno} on loan #{lid}"
        if op == "delete":
            lid = int(keys["loan_id"])
            dno = int(keys["disbursement_no"])
            crud_loans.delete_disbursement(db, lid, dno)
            audit(f"disbursement delete loan={lid} no={dno}", "LoanDisbursement")
            return [{"loan_id": lid, "disbursement_no": dno}], "Disbursement", "Removed disbursement"

    if entity == "repayment":
        if op == "delete":
            lid = int(keys["loan_id"])
            rno = int(keys["repayment_no"])
            crud_loans.delete_repayment(db, lid, rno)
            audit(f"repayment delete loan={lid} no={rno}", "Repayment")
            return [{"loan_id": lid, "repayment_no": rno}], "Repayment", "Removed repayment"

    raise HTTPException(400, detail=f"Mutation not implemented: {entity} {op}")


# ---------------------------------------------------------------------------
# execute_action
# ---------------------------------------------------------------------------

def execute_action(
    db: Session, user_id: int, role: str, plan: NLQueryPlan
) -> Tuple[List[Dict[str, Any]], str, str]:
    from app.services.financial_service import process_disbursement, process_repayment

    _require_admin_nl(role)
    ab = dict(plan.action_body or {})

    if plan.action == "process_disbursement":
        if "loan_id" not in ab or "imf_account_id" not in ab:
            raise HTTPException(400, detail="loan_id and imf_account_id required for disbursement")
        obj = process_disbursement(
            db,
            loan_id=int(ab["loan_id"]),
            imf_account_id=int(ab["imf_account_id"]),
            amount=Decimal(str(ab.get("amount", 0))),
            disbursement_date=ab.get("disbursement_date"),
            actor_user_id=user_id,
        )
        return [_orm_row_dict(obj)], "Disbursement", f"Recorded disbursement for loan #{ab['loan_id']}"

    if plan.action == "process_repayment":
        obj = process_repayment(
            db,
            loan_id=int(ab["loan_id"]),
            amount_paid=Decimal(str(ab.get("amount_paid", ab.get("amount", 0)))),
            payment_date=ab.get("payment_date"),
            actor_user_id=user_id,
        )
        return (
            [{"loan_id": obj.loan_id, "repayment_no": obj.repayment_no}],
            "Repayment",
            f"Recorded repayment for loan #{obj.loan_id}",
        )

    raise HTTPException(400, detail=f"Unknown action: {plan.action}")


# ---------------------------------------------------------------------------
# Unsupported response
# ---------------------------------------------------------------------------

def _unsupported_dashboard(note: str) -> DashboardResponse:
    meta = DashboardMetadata(module="unsupported", applied_filters=[], group_by=[], row_count=0)
    return DashboardResponse(
        title="Unsupported query",
        chart_type="table",
        summary=note,
        data=[],
        metadata=meta,
    )


def _tag_planner(resp: DashboardResponse, planner: str) -> DashboardResponse:
    """Expose whether Groq or offline rules produced the plan (metadata.planner)."""
    return resp.model_copy(
        update={"metadata": resp.metadata.model_copy(update={"planner": planner})}
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_unified_nl_query(
    db: Session,
    user_id: int,
    role: str,
    query: str,
    conversation: Optional[List[Dict[str, Any]]] = None,
) -> DashboardResponse:
    """
    Top-level NL → DashboardResponse pipeline.

    Flow:
    1. Injection check.
    2. Build threaded user block (current query + conversation history).
    3. Call AI planner (Groq) with full conversation context.
    4. If AI unavailable, fall back to rule-based router (NL_RULE_FALLBACK=true).
    5. Detect export intent from plan or conversation wording.
    6. Dispatch to browse / aggregate / mutate / action executor.
    7. Inject DB-driven geography filters for aggregates with region constraints.
    8. Generate Groq NL summary.
    9. Wire chart type from user wording.
    10. Surface export URL in response if requested.
    """
    _check_injection(query.strip())

    from app.services.report_generation_service import (
        build_report_dashboard_response,
        is_structured_report_prompt,
    )

    if is_structured_report_prompt(query.strip()):
        return build_report_dashboard_response(db, query.strip())

    conv = conversation or []
    # Build the combined user block once — used for both planning and summarisation
    threaded_for_llm = llm_svc.nl_conversation_user_block(query.strip(), conv)
    context_lc = _flatten_nl_context_lower(query.strip(), conv)

    llm_svc.ensure_analytics_dotenv()

    def _env_on(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in ("1", "true", "yes", "on")

    # Groq plans the query; regex rules only when Groq is unavailable (rate limit / outage).
    rules_fallback = _env_on("NL_RULE_FALLBACK", default=True)
    planner_source = "groq"
    plan = llm_svc.resolve_nl_query_plan(query.strip(), role, conversation=conv or None)

    if plan is None and rules_fallback:
        failure = llm_svc.get_last_planner_failure()
        if failure and failure.code == "rate_limit":
            return _unsupported_dashboard(failure.message)

        from app.services.nl_rule_fallback import legacy_rule_nl_plan

        planner_source = "rules"
        plan = legacy_rule_nl_plan(query.strip(), role)
        logger.warning("NL planner: Groq unavailable — rule fallback for %r", query.strip()[:120])
    elif plan is not None:
        logger.info("NL planner: Groq plan kind=%s", (plan.kind or "?"))

    if plan is None:
        failure = llm_svc.get_last_planner_failure()
        if failure is not None:
            note = failure.message
            if failure.detail and failure.code != "rate_limit":
                note = f"{failure.message} ({failure.detail[:200]})"
        elif not os.getenv("GROQ_API_KEY", "").strip():
            note = (
                "Groq is required for natural-language queries. "
                "Set GROQ_API_KEY in app/.env and restart uvicorn."
            )
        else:
            note = (
                "Groq could not plan this question. Check server logs, wait if you hit a rate limit, "
                "or set GROQ_ANALYTICS_MODEL=llama-3.1-8b-instant in app/.env."
            )
        return _unsupported_dashboard(note)

    kind = (plan.kind or "aggregate").lower()

    if kind == "unsupported":
        return _unsupported_dashboard(plan.note or "This request cannot be executed here.")

    # Export intent: current message only — never inherit export_format from Groq/plan via old chat turns
    from app.services.report_generation_service import is_structured_report_prompt

    if is_structured_report_prompt(query.strip()):
        export_format: Optional[str] = "pdf"
    else:
        export_format = _detect_export_format(query.strip())

    # ── browse ────────────────────────────────────────────────────────────
    if kind == "browse":
        data, title, summary = execute_browse(db, role, user_id, plan, nl_question=query.strip())

        ai_sum = llm_svc.try_groq_nl_answer_summary(
            threaded_for_llm, "browse", title, data, summary
        )
        if ai_sum:
            summary = ai_sum

        meta = DashboardMetadata(
            module=f"browse:{plan.browse_entity}",
            applied_filters=[f.model_dump() for f in plan.browse_filters],
            row_count=len(data),
            planner=planner_source,
        )
        resp = DashboardResponse(
            title=title,
            chart_type="table",
            summary=summary,
            data=data,
            metadata=meta,
        )

        # Wire chart if user asked for a visualisation
        if (
            _nl_wants_visual_chart(context_lc)
            or _nl_wants_line_chart(context_lc)
            or _nl_wants_pie_chart(context_lc)
        ):
            xx, yy, ct = _infer_browse_chart_axes(data)
            if xx and yy and ct != "table":
                if _nl_wants_line_chart(context_lc):
                    out_ct = "line"
                elif _nl_wants_pie_chart(context_lc):
                    out_ct = "pie"
                else:
                    out_ct = ct
                resp = resp.model_copy(update={"chart_type": out_ct, "x_axis": xx, "y_axis": yy})

        resp = _apply_nl_chart_overrides(context_lc, resp)
        return _tag_planner(_attach_export_format(resp, export_format), planner_source)

    # ── mutate ────────────────────────────────────────────────────────────
    if kind == "mutate":
        rows, title, summary = execute_mutate(db, user_id, role, plan, nl_question=query.strip())
        ai_sum = llm_svc.try_groq_nl_answer_summary(threaded_for_llm, "mutate", title, rows, summary)
        if ai_sum:
            summary = ai_sum
        meta = DashboardMetadata(
            module=f"mutate:{plan.mutate_entity}",
            applied_filters=[],
            row_count=len(rows),
            planner=planner_source,
        )
        return DashboardResponse(title=title, chart_type="table", summary=summary, data=rows, metadata=meta)

    # ── action ────────────────────────────────────────────────────────────
    if kind == "action":
        rows, title, summary = execute_action(db, user_id, role, plan)
        ai_sum = llm_svc.try_groq_nl_answer_summary(threaded_for_llm, "action", title, rows, summary)
        if ai_sum:
            summary = ai_sum
        meta = DashboardMetadata(
            module=f"action:{plan.action}", row_count=len(rows), planner=planner_source
        )
        return DashboardResponse(title=title, chart_type="table", summary=summary, data=rows, metadata=meta)

    # ── aggregate ─────────────────────────────────────────────────────────
    if not plan.aggregate:
        plan = NLQueryPlan(kind="aggregate", aggregate=parse_natural_language_query(query.strip()))

    spec = plan.aggregate

    # 1. Fix mis-planned rollups (e.g. loan count per program)
    spec = _coerce_aggregate_plan(spec, query.strip())

    # 2. Cross-module metrics (GDP + loan_amount) → country module with FK joins
    spec = _remap_cross_module_aggregate(spec)

    # 2. Expand scalar → grouped when user wants a chart
    spec = _expand_scalar_aggregate_for_visualization(role, context_lc, spec)

    # 3. Resolve any region filters (e.g. region ilike "%Europe%") to country names via DB
    spec = _inject_region_filters_from_db(db, context_lc, spec)

    # 3. Set chart type from user wording
    spec = _prefer_aggregate_chart_type(context_lc, spec)

    # 4. Permission sanitisation
    spec = validate_and_sanitise_spec(role, spec)

    # 5. Execute
    raw_rows = build_and_execute(db, spec)

    # 6. AI summary
    summary = llm_svc.generate_nl_summary(threaded_for_llm, spec, raw_rows)

    # 7. Build response
    dash = build_dashboard_response(spec, raw_rows, original_query=query, summary=summary)
    dash = _apply_nl_chart_overrides(context_lc, dash)
    return _tag_planner(_attach_export_format(dash, export_format), planner_source)
