"""
services/query_parser_service.py — Rule-based natural language → AnalyticsSpec.

Used as a fallback when Groq + LangChain planning is unavailable or fails.
The primary interpretation path is app.services.analytics_llm_service.try_parse_with_groq.

SECURITY:
  - Input is sanitised for injection patterns before parsing.
  - Output is a typed AnalyticsSpec — never raw SQL or Python.
  - Unknown intent → safe default spec, not an error that leaks schema.

PROMPT INJECTION DEFENCES:
  Inputs matching known attack patterns are rejected immediately with a
  generic 400 error that does not reveal why the query was blocked.
"""

import re
from typing import List, Optional, Tuple

from fastapi import HTTPException, status

from app.analytics_schemas.analytics import AnalyticsSpec, MetricSpec, FilterSpec, SortSpec


# ── Injection / jailbreak pattern blocklist ────────────────────────────────────

_INJECTION_PATTERNS: List[re.Pattern] = [
    # SQL injection (context-aware — allow NL verbs like "update X to Y", "delete user2")
    re.compile(r"\bDROP\s+(?:TABLE|DATABASE|INDEX|SCHEMA)\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\s+[\w.]+\s+SET\b", re.IGNORECASE),
    re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
    re.compile(r"\b(?:TRUNCATE|ALTER)\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bGRANT\b|\bREVOKE\b", re.IGNORECASE),
    re.compile(r"\bUNION\s+SELECT\b", re.IGNORECASE),
    re.compile(r"--\s*$", re.MULTILINE),
    re.compile(r";\s*(SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE),
    # Schema probing
    re.compile(r"\b(information_schema|pg_catalog|pg_tables|sys\.tables)\b", re.IGNORECASE),
    re.compile(r"\bshow\s+(all\s+)?tables\b", re.IGNORECASE),
    re.compile(r"\breveal\s+schema\b", re.IGNORECASE),
    re.compile(r"\bdump\s+(database|tables|schema)\b", re.IGNORECASE),
    # Prompt override
    re.compile(r"\bignore\s+(previous|all|prior)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\bforget\s+(your|all|previous)\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(a\s+)?(?:different|new|another)\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bsystem\s*prompt\b", re.IGNORECASE),
]


def _check_injection(query: str) -> None:
    """Raise 400 (opaque) if the query matches any injection/jailbreak pattern."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(query):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query could not be processed. Please rephrase your question.",
            )


def _metric_phrase_in_text(phrase: str, text: str) -> bool:
    """
    Match a metric keyword without false positives (e.g. 'count' inside 'countries').
    Multi-word phrases use substring match; single tokens use word boundaries.
    """
    phrase = phrase.strip().lower()
    if not phrase:
        return False
    hay = text.lower()
    if " " in phrase:
        return phrase in hay
    return bool(re.search(rf"\b{re.escape(phrase)}\b", hay))


# ── Keyword → module mapping ───────────────────────────────────────────────────

_MODULE_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("country", [
        "compare gdp", "gdp and loan", "loan amount and gdp",
        "imf loan amount", "per country", "all countries",
    ]),
    ("economic", [
        "gdp", "inflation", "cpi", "economic", "exchange rate",
        "industrial output", "agricultural", "money supply", "indicator",
    ]),
    ("repayment", [
        "repayment", "repaid", "overdue", "outstanding balance",
        "amount paid", "payment",
    ]),
    ("installment", [
        "installment", "due date", "schedule", "overdue installment",
    ]),
    ("transaction", [
        "transaction", "financial transaction", "transfer", "disbursement transaction",
    ]),
    ("loan", [
        "loan", "loans", "sovereign", "lending", "credit", "disbursement", "borrow",
        "active loan", "approved", "interest rate",
    ]),
    ("user", [
        "user", "officer", "analyst", "admin", "staff",
    ]),
]

_DEFAULT_METRICS: dict = {
    "country":     MetricSpec(field="loan_amount",  aggregation="sum"),
    "loan":        MetricSpec(field="loan_amount",  aggregation="sum"),
    "economic":    MetricSpec(field="GDP",           aggregation="avg"),
    "repayment":   MetricSpec(field="amount_paid",   aggregation="sum"),
    "installment": MetricSpec(field="amount_due",    aggregation="sum"),
    "transaction": MetricSpec(field="amount",        aggregation="sum"),
    "user":        MetricSpec(field="user_id",       aggregation="count"),
}

_METRIC_KEYWORDS: dict = {
    # phrase → (model field name, default aggregation)
    # ORDER MATTERS: longer/more-specific phrases first
    "exchange rate":      ("exchange_rate",      "avg"),
    "interest rate":      ("interest_rate",      "avg"),
    "industrial output":  ("industrial_output",  "avg"),
    "loan amount":        ("loan_amount",        "sum"),
    "amount paid":        ("amount_paid",        "sum"),
    "outstanding":        ("outstanding_balance","avg"),
    "amount due":         ("amount_due",         "sum"),
    "transaction amount": ("amount",             "sum"),
    "inflation":          ("inflation",          "avg"),
    "gdp":                ("GDP",                "avg"),
    "cpi":                ("CPI",                "avg"),
    "count":              (None,                 "count"),  # special: count pk
}

_GROUP_KEYWORDS: dict = {
    # country variations (handles typos like "countr")
    "by countr":    "country_name",
    "per countr":   "country_name",
    "by country":   "country_name",
    "per country":  "country_name",
    "countries":    "country_name",
    "country wise": "country_name",
    "countrywise":  "country_name",
    "member country": "country_name",
    "member countries": "country_name",
    "by member": "country_name",
    # status
    "by status":    "status",
    "per status":   "status",
    # program
    "by program":   "program_name",
    "per program":  "program_name",
    "each program": "program_name",
    "under each":   "program_name",
    # type
    "by type":      "transaction_type",
    "per type":     "transaction_type",
    # loan
    "by loan":      "loan_id",
    "per loan":     "loan_id",
}

# Status values match Title Case exactly as stored in the database
_FILTER_KEYWORDS: List[Tuple[str, FilterSpec]] = [
    ("active",    FilterSpec(field="status", operator="=", value="Active")),
    ("overdue",   FilterSpec(field="status", operator="=", value="Overdue")),
    ("completed", FilterSpec(field="status", operator="=", value="Completed")),
    ("approved",  FilterSpec(field="status", operator="=", value="Approved")),
    ("pending",   FilterSpec(field="status", operator="=", value="Pending")),
]

_CHART_KEYWORDS: List[Tuple[str, str]] = [
    ("pie chart", "pie"),
    ("pie graph", "pie"),
    ("line chart", "line"),
    ("line graph", "line"),
    ("bar chart", "bar"),
    ("bar graph", "bar"),
    ("area chart", "area"),
    ("pie", "pie"),
    ("line", "line"),
    ("area", "area"),
    ("table", "table"),
    ("bar", "bar"),
]

_SORT_KEYWORDS: List[Tuple[str, str]] = [
    ("highest",  "desc"),
    ("top",      "desc"),
    ("largest",  "desc"),
    ("most",     "desc"),
    ("lowest",   "asc"),
    ("smallest", "asc"),
    ("least",    "asc"),
    ("bottom",   "asc"),
]

_DATE_RANGE_PATTERNS: List[Tuple[re.Pattern, int]] = [
    (re.compile(r"last\s+(\d+)\s+year", re.IGNORECASE), None),   # captured group
    (re.compile(r"past\s+(\d+)\s+year", re.IGNORECASE), None),
    (re.compile(r"last\s+year",   re.IGNORECASE), 1),
    (re.compile(r"last\s+month",  re.IGNORECASE), 0),   # 0 = current year
    (re.compile(r"this\s+year",   re.IGNORECASE), 0),
]


def _detect_module(text: str) -> str:
    """Return the best-matching module name from the query text."""
    for module, keywords in _MODULE_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return module
    return "loan"   # safe default


def _detect_metrics(text: str, module: str) -> List[MetricSpec]:
    """Extract metric specs from text; fall back to the module default."""
    metrics = []
    for phrase, (field, agg) in _METRIC_KEYWORDS.items():
        if _metric_phrase_in_text(phrase, text):
            if field is None:
                # "count" keyword — count the primary key
                from app.core.analytics_registry import ANALYTICS_REGISTRY
                pk = ANALYTICS_REGISTRY.get(module, {}).get("pk", "loan_id")
                metrics.append(MetricSpec(field=pk, aggregation="count"))
            else:
                metrics.append(MetricSpec(field=field, aggregation=agg))

    # Aggregation override keywords
    agg_map = {
        "average": "avg", "mean": "avg", "avg": "avg",
        "total": "sum", "sum": "sum",
        "count": "count",
        "minimum": "min", "min": "min",
        "maximum": "max", "max": "max",
    }
    for word, agg in agg_map.items():
        if _metric_phrase_in_text(word, text) and metrics:
            # Apply override aggregation to all detected metrics
            metrics = [MetricSpec(field=m.field, aggregation=agg) for m in metrics]
            break

    if not metrics:
        metrics = [_DEFAULT_METRICS[module]]

    # Deduplicate
    seen = set()
    unique = []
    for m in metrics:
        key = (m.field, m.aggregation)
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


def _detect_group_by(text: str) -> List[str]:
    groups = []
    seen = set()
    for phrase, field in _GROUP_KEYWORDS.items():
        if phrase in text and field not in seen:
            groups.append(field)
            seen.add(field)
    return groups


def _detect_filters(text: str) -> List[FilterSpec]:
    filters = []
    for keyword, f in _FILTER_KEYWORDS:
        if keyword in text:
            filters.append(f)
    return filters


def _detect_chart_type(text: str) -> str:
    for keyword, chart in _CHART_KEYWORDS:
        if keyword in text:
            return chart
    return "bar"


def _detect_sort(text: str, metrics: List[MetricSpec]) -> Optional[SortSpec]:
    hay = text.lower()
    for keyword, direction in _SORT_KEYWORDS:
        if keyword in hay:
            sort_field = metrics[0].field if metrics else "loan_amount"
            if "inflation" in hay and any(m.field == "inflation" for m in metrics):
                sort_field = "inflation"
            elif "cpi" in hay and any(m.field == "CPI" for m in metrics):
                sort_field = "CPI"
            return SortSpec(field=sort_field, direction=direction)
    return None


def _detect_date_filters(text: str, module: str) -> List[FilterSpec]:
    """
    Time-window filters mapped to each module's date_field (registry).
    Prefer 'last N months' when present; otherwise year-style phrases.
    """
    import datetime

    from app.core.analytics_registry import get_module

    entry = get_module(module) or {}
    date_field = entry.get("date_field")
    if not date_field:
        return []

    hay = text.lower().strip()
    filters: List[FilterSpec] = []

    m_months = re.search(r"\b(?:last|past)\s+(\d+)\s+months?\b", hay, re.IGNORECASE)
    if m_months:
        try:
            n = int(m_months.group(1))
            n = min(max(n, 1), 120)
            start = datetime.date.today() - datetime.timedelta(days=30 * n)
            return [FilterSpec(field=date_field, operator=">=", value=start)]
        except ValueError:
            pass

    current_year = datetime.date.today().year
    for pattern, static_years in _DATE_RANGE_PATTERNS:
        m = pattern.search(hay)
        if m:
            if static_years is None:
                try:
                    n_years = int(m.group(1))
                    year = current_year - n_years
                except (IndexError, ValueError):
                    year = current_year - 1
            elif static_years == 0:
                year = current_year
            else:
                year = current_year - static_years
            filters.append(
                FilterSpec(
                    field=date_field,
                    operator=">=",
                    value=datetime.date(year, 1, 1),
                )
            )
            break

    return filters


def _detect_limit(text: str) -> int:
    """Extract explicit top-N limits from text."""
    patterns = [
        r"\btop\s+(\d+)\b",
        r"\btop(\d+)\b",
        r"\bfirst\s+(\d+)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                n = int(m.group(1))
                return min(max(n, 1), 100)
            except ValueError:
                continue
    return 10


# ── Public entry point ─────────────────────────────────────────────────────────

def parse_natural_language_query(query: str) -> AnalyticsSpec:
    """
    Parse a free-text analytics question into a structured AnalyticsSpec.

    Steps:
      1. Injection / jailbreak check
      2. Normalise text
      3. Detect module
      4. Detect metrics
      5. Detect group-by
      6. Detect filters (status + date range)
      7. Detect chart type
      8. Detect sort
      9. Detect limit
      10. Assemble and return AnalyticsSpec

    Raises:
        HTTPException 400 — if query is empty, too long, or matches injection pattern.
    """
    # Step 1: security check
    _check_injection(query)

    # Step 2: normalise
    text = query.lower().strip()
    # Collapse extra whitespace
    text = re.sub(r"\s+", " ", text)

    # Step 3-9: detect components
    module      = _detect_module(text)
    metrics     = _detect_metrics(text, module)
    group_by    = _detect_group_by(text)
    filters     = _detect_filters(text)
    date_f      = _detect_date_filters(text, module)
    chart_type  = _detect_chart_type(text)
    sort        = _detect_sort(text, metrics)
    limit       = _detect_limit(text)

    # Merge date filters (avoid duplicate field)
    filter_fields = {f.field for f in filters}
    for df in date_f:
        if df.field not in filter_fields:
            filters.append(df)

    # If grouped, default sort on first metric if none detected
    if group_by and sort is None and metrics:
        sort = SortSpec(field=metrics[0].field, direction="desc")

    return AnalyticsSpec(
        module=module,
        metrics=metrics,
        group_by=group_by,
        filters=filters,
        chart_type=chart_type,
        sort=sort,
        limit=limit,
        offset=0,
    )
