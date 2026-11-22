"""
Groq + LangChain structured parsing for fiscal analytics questions.

Produces the same AnalyticsSpec as the rule-based parser so the existing
permission layer and ORM query builder stay the single execution path.

Also exposes NLQueryPlan parsing for unified browse/mutate/action routing.

Design principles:
- No hardcoded country rosters, field lists, or region names anywhere in this file.
- All geography comes from the live DB at query time.
- Multi-turn conversation is merged into every LLM call so follow-up questions work.
- Export intent (PDF / CSV) is detected and surfaced in the plan.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default: smaller model = fewer tokens per request (helps stay under Groq free-tier TPD).
_DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
_LEGACY_GROQ_MODEL = "llama-3.3-70b-versatile"


@dataclass(frozen=True)
class NLPlannerFailure:
    """Why Groq planning failed — surfaced to the UI instead of a generic message."""

    code: str  # missing_key | rate_limit | api_error | parse_error
    message: str
    detail: str = ""


_last_planner_failure: Optional[NLPlannerFailure] = None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _groq_nl_summary_enabled() -> bool:
    """Extra Groq call per answer — off by default to preserve free-tier quota."""
    return _env_flag("GROQ_NL_SUMMARY", default=False)


def get_last_planner_failure() -> Optional[NLPlannerFailure]:
    return _last_planner_failure


def _set_planner_failure(failure: Optional[NLPlannerFailure]) -> None:
    global _last_planner_failure
    _last_planner_failure = failure


# ---------------------------------------------------------------------------
# .env loader — runs at import time so GROQ_API_KEY is visible regardless of cwd
# ---------------------------------------------------------------------------

def ensure_analytics_dotenv() -> None:
    """Load `app/.env` so GROQ_API_KEY is set even when uvicorn cwd or OS env differs."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    app_env = Path(__file__).resolve().parents[1] / ".env"
    if app_env.is_file():
        # Must override: Windows/user env often keeps an old invalid GROQ_API_KEY
        load_dotenv(app_env, override=True)
        return

    for path in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if path.is_file():
            load_dotenv(path, override=True)
            return


ensure_analytics_dotenv()

from app.analytics_schemas.analytics import AnalyticsSpec, FilterSpec
from app.core.allowed_fields import ALLOWED_FIELDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def nl_conversation_user_block(
    current_question: str,
    conversation: Optional[List[Dict[str, Any]]],
) -> str:
    """
    Merge prior chat turns + latest user message into one LLM user block.

    The last 12 turns are included (truncated at 1 200 chars each) so
    follow-up questions like "also show GDP" resolve correctly.
    """
    cur = current_question.strip()
    if not conversation:
        return cur

    lines: List[str] = []
    for turn in conversation[-12:]:
        role_raw = str(turn.get("role", "user")).strip().upper()
        label = role_raw if role_raw in {"USER", "ASSISTANT"} else "MESSAGE"
        txt = str(turn.get("content", "")).strip().replace("\n\n", "\n")
        if not txt:
            continue
        if len(txt) > 1_200:
            txt = txt[:1_200] + "…"
        lines.append(f"{label}: {txt}")

    if not lines:
        return cur

    transcript = "\n".join(lines)
    return (
        "MULTI-TURN CHAT CONTEXT (earlier turns — use these to resolve follow-up references "
        "like 'those countries', 'also show', 'same filter', 'add GDP column'):\n"
        f"{transcript}\n\n"
        f"LATEST USER MESSAGE (primary instruction — fulfil this):\n{cur}"
    )


def _canonical_filter_op(operator: Optional[str]) -> str:
    """Normalise any operator synonym the LLM might emit to our canonical set."""
    o = (operator or "=").strip().lower()
    return {
        "eq": "=",
        "ne": "!=",
        "neq": "!=",
        "gte": ">=",
        "lte": "<=",
        "gt": ">",
        "lt": "<",
        "in": "in",
        "like": "ilike",
        "ilike": "ilike",
    }.get(o, o if o else "=")


# Expose under the old name so unified_nl_service imports don't break
_canonical_browse_filter_op = _canonical_filter_op
_canonical_aggregate_filter_op = _canonical_filter_op


def _role_capability_text(role: str) -> str:
    """
    Describe which modules and fields the authenticated role may use.
    Derived entirely from ALLOWED_FIELDS — no hardcoding here.
    """
    role = (role or "").strip().lower()
    per_mod = ALLOWED_FIELDS.get(role, {})
    if not per_mod:
        return f"Role {role!r} has no analytics modules configured."
    lines: List[str] = []
    for module, fields in sorted(per_mod.items()):
        lines.append(f"- module {module!r}: fields {fields}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core Groq invocations
# ---------------------------------------------------------------------------

def _groq_models_to_try() -> List[str]:
    """Primary model only unless GROQ_ENABLE_MODEL_FALLBACK=true (saves quota on errors)."""
    primary = os.getenv("GROQ_ANALYTICS_MODEL", _DEFAULT_GROQ_MODEL).strip() or _DEFAULT_GROQ_MODEL
    if not _env_flag("GROQ_ENABLE_MODEL_FALLBACK", default=False):
        return [primary]

    fallback = (os.getenv("GROQ_FALLBACK_MODEL") or "").strip()
    seen: Set[str] = set()
    out: List[str] = []
    for name in (primary, fallback, _DEFAULT_GROQ_MODEL):
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out or [primary]


def _groq_llm(model: str, max_tokens: int = 1_000):
    """Return a configured ChatGroq instance or raise ImportError / ValueError."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")
    from langchain_groq import ChatGroq  # type: ignore

    return ChatGroq(api_key=api_key, model=model, temperature=0, max_tokens=max_tokens)


def _rate_limit_user_message(exc_text: str) -> str:
    import re

    wait_hint = ""
    m = re.search(r"try again in ([0-9]+m[0-9.]*s|[0-9.]+s)", exc_text, re.IGNORECASE)
    if m:
        wait_hint = f" Groq says try again in {m.group(1)}."
    elif "tokens per day" in exc_text.lower() or "tpd" in exc_text.lower():
        wait_hint = " Daily token quota is exhausted — wait until it resets or use another API key."
    else:
        wait_hint = " Wait a few minutes and retry."

    return (
        "Groq rate limit reached, so this question could not be planned by AI."
        f"{wait_hint} Restart uvicorn after changing GROQ_API_KEY in app/.env."
        " Upgrade: https://console.groq.com/settings/billing"
    )


def _classify_groq_error(exc: Exception) -> NLPlannerFailure:
    err_name = type(exc).__name__
    text = str(exc)
    low = text.lower()
    if (
        "rate_limit" in err_name.lower()
        or "429" in text
        or "rate limit" in low
        or "rate_limit_exceeded" in low
    ):
        return NLPlannerFailure(
            code="rate_limit",
            message=_rate_limit_user_message(text),
            detail=text[:500],
        )
    if "invalid_api_key" in low or "401" in text or "authentication" in low:
        return NLPlannerFailure(
            code="missing_key",
            message=(
                "Groq API key is invalid. Set GROQ_API_KEY in app/.env, remove any old "
                "GROQ_API_KEY from Windows environment variables, then stop uvicorn (Ctrl+C) "
                "and start it again — reload alone may keep a stale key."
            ),
            detail=text[:500],
        )
    return NLPlannerFailure(
        code="api_error",
        message="Groq could not complete this request. See server logs for details.",
        detail=text[:500],
    )


def _invoke_structured_groq(system: str, user: str, schema: Type[T]) -> Optional[T]:
    """
    Invoke Groq + LangChain structured output for schema T.
    Tries each configured model in order (primary → fallback → defaults).
    """
    from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore

    if not os.getenv("GROQ_API_KEY", "").strip():
        _set_planner_failure(
            NLPlannerFailure(
                code="missing_key",
                message="GROQ_API_KEY is not set. Add it to app/.env and restart uvicorn.",
            )
        )
        return None

    last_failure: Optional[NLPlannerFailure] = None
    for model in _groq_models_to_try():
        try:
            llm = _groq_llm(model)
            structured = llm.with_structured_output(schema)
            out = structured.invoke([SystemMessage(content=system), HumanMessage(content=user)])
            if isinstance(out, schema):
                _set_planner_failure(None)
                return out
            parsed = schema.model_validate(out)  # type: ignore[attr-defined]
            _set_planner_failure(None)
            logger.info("Groq structured plan OK (model=%s, schema=%s)", model, schema.__name__)
            return parsed
        except (ImportError, ValueError) as exc:
            last_failure = NLPlannerFailure(
                code="missing_key",
                message=str(exc),
            )
            logger.warning("Groq unavailable: %s", exc)
            break
        except Exception as exc:
            last_failure = _classify_groq_error(exc)
            logger.warning(
                "Groq structured parse failed (model=%s, schema=%s): %s",
                model,
                getattr(schema, "__name__", schema),
                exc,
            )
            # Do not burn quota retrying other models on rate limit or auth errors
            if last_failure.code in ("rate_limit", "missing_key"):
                break
            continue

    _set_planner_failure(last_failure)
    return None


# ---------------------------------------------------------------------------
# AnalyticsSpec (aggregate) parsing
# ---------------------------------------------------------------------------

def try_parse_with_groq(query: str, role: str) -> Optional[AnalyticsSpec]:
    """
    Map an NL string → AnalyticsSpec for aggregate charts/tables.

    The system prompt is intentionally free of hardcoded country / region lists;
    geography constraints are injected at query-execution time from the live DB.
    """
    text = query.strip()
    if not text:
        return None

    capability = _role_capability_text(role)

    system = f"""You are a query planner for an IMF fiscal database (PostgreSQL via ORM).
Output ONLY a machine-readable AnalyticsSpec object — no SQL, no Python, no prose.

Authenticated role: {role!r}
Permitted modules and fields (ONLY use these — nothing else):
{capability}

Rules:
- module must be one of the modules listed above for this role.
- metrics: list of {{field, aggregation}}. aggregation ∈ {{count, sum, avg, min, max}}.
- group_by: list of field names. Use ["country_name"] for per-country breakdowns.
- filters: list of {{field, operator, value}}.
  operator ∈ {{=, !=, >, <, >=, <=, in, ilike}}.
  Use ilike with wildcard patterns (e.g. "%Europe%") for partial text matches.
  NEVER hardcode a list of country names — the execution layer resolves geography from the DB.
- sort: sort by a metric field for top-N rankings.
- limit: integer 1–1 000 for top-N queries.
- chart_type: "bar" for category comparisons; "line" for line graph/chart/plot or time-series;
  "pie" for pie graph/chart; "table" only when no chart/graph/plot is requested.
  Honour phrases like "line graph", "pie graph", "give me a line chart", "create pie chart".

Geography rule:
- When the user mentions a region (Europe, Asia, etc.) on an economic module,
  emit a filter: field="region", operator="ilike", value="%<RegionWord>%".
  The execution layer will resolve this to actual country names via the DB — do NOT
  enumerate countries yourself.

Multi-turn rule:
- If the prompt contains MULTI-TURN CHAT CONTEXT, use earlier turns to resolve
  references like "those countries", "same filters", "also show GDP".
  The LATEST USER MESSAGE is the primary instruction.
"""

    spec = _invoke_structured_groq(system, text, AnalyticsSpec)
    if spec is None:
        return None
    try:
        return _normalize_spec(spec)
    except Exception as exc:
        logger.warning("Normalising Groq AnalyticsSpec failed: %s", exc)
        _set_planner_failure(
            NLPlannerFailure(code="parse_error", message="Groq returned an invalid analytics plan.", detail=str(exc))
        )
        return None


# ---------------------------------------------------------------------------
# NLQueryPlan parsing
# ---------------------------------------------------------------------------

def try_nl_plan_with_groq(query: str, role: str):
    """
    Full unified NLQueryPlan via Groq + LangChain structured output.
    Returns None only when the API/key fails; never uses offline regex routing.
    """
    from app.analytics_schemas.nl_plan import NLQueryPlan as Plan
    from app.services.nl_planner_prompt import build_nl_plan_system_prompt

    text = (query or "").strip()
    if not text:
        return None

    capability = _role_capability_text(role)
    system = build_nl_plan_system_prompt(role, capability)
    raw = _invoke_structured_groq(system, text, Plan)
    if raw is None:
        return None
    try:
        return _finalize_nl_plan(raw)
    except Exception as exc:
        logger.warning("Finalizing Groq NLQueryPlan failed: %s", exc, exc_info=True)
        _set_planner_failure(
            NLPlannerFailure(code="parse_error", message="Groq returned an invalid query plan.", detail=str(exc))
        )
        return None


def resolve_nl_query_plan(
    query: str,
    role: str,
    conversation: Optional[List[Dict[str, Any]]] = None,
):
    """
    AI planner: one Groq structured call (NLQueryPlan).

    A second AnalyticsSpec Groq call is opt-in only (GROQ_AGGREGATE_FALLBACK=true)
    because it doubles API usage and quickly exhausts free-tier limits.
    """
    from app.analytics_schemas.nl_plan import NLQueryPlan

    ensure_analytics_dotenv()
    _set_planner_failure(None)

    planner_user = nl_conversation_user_block(query.strip(), conversation)

    plan = try_nl_plan_with_groq(planner_user, role)
    if plan is not None:
        return plan

    failure = get_last_planner_failure()
    if failure and failure.code == "rate_limit":
        return None

    if not os.getenv("GROQ_API_KEY", "").strip():
        return None

    if not _env_flag("GROQ_AGGREGATE_FALLBACK", default=False):
        return None

    spec = try_parse_with_groq(planner_user, role)
    if spec is not None:
        return NLQueryPlan(kind="aggregate", aggregate=spec)
    return None


# ---------------------------------------------------------------------------
# Spec / Plan normalisation
# ---------------------------------------------------------------------------

def _normalize_spec(spec: AnalyticsSpec) -> AnalyticsSpec:
    """Canonicalise aggregations, operators, limits, offsets."""
    metrics = [
        type(m).model_validate({"field": m.field, "aggregation": (m.aggregation or "avg").lower()})
        for m in spec.metrics
    ]

    sort = spec.sort
    if sort is not None:
        sort = type(sort).model_validate(
            {"field": sort.field, "direction": (sort.direction or "desc").lower()}
        )

    limit = spec.limit
    if limit is not None:
        limit = max(1, min(int(limit), 1_000))

    filters = [
        FilterSpec(field=f.field, operator=_canonical_filter_op(f.operator), value=f.value)
        for f in spec.filters
    ]

    c_raw = (spec.chart_type or "").strip().lower()
    chart = c_raw if c_raw else "bar"

    return AnalyticsSpec(
        module=spec.module.strip().lower(),
        metrics=metrics,
        group_by=list(spec.group_by),
        filters=filters,
        chart_type=chart,
        sort=sort,
        limit=limit,
        offset=max(0, int(spec.offset or 0)),
    )


def _finalize_nl_plan(plan):
    """Normalise kind, action spelling, filter operators, and nested AnalyticsSpec."""
    from app.analytics_schemas.nl_plan import NLQueryPlan as Plan

    if not isinstance(plan, Plan):
        plan = Plan.model_validate(plan)

    # kind
    kind = (plan.kind or "aggregate").strip().lower()
    plan = plan.model_copy(update={"kind": kind})

    # action typo fixes
    act = (plan.action or "").strip().lower().replace(" ", "_").replace("-", "_")
    act_fix = {"process_repacement": "process_repayment"}.get(act, act)
    plan = plan.model_copy(update={"action": act_fix})

    # normalise browse filter operators
    browse_norm = [
        FilterSpec(field=f.field, operator=_canonical_filter_op(f.operator), value=f.value)
        for f in (plan.browse_filters or [])
    ]
    plan = plan.model_copy(update={"browse_filters": browse_norm})

    if kind == "aggregate" and plan.aggregate:
        plan = plan.model_copy(update={"aggregate": _normalize_spec(plan.aggregate)})

    exp = (plan.export_format or "").strip().lower()
    if exp in ("pdf", "csv"):
        plan = plan.model_copy(update={"export_format": exp})
    elif exp:
        plan = plan.model_copy(update={"export_format": None})

    return plan


# ---------------------------------------------------------------------------
# NL answer summary (Groq prose generation)
# ---------------------------------------------------------------------------

def try_groq_nl_answer_summary(
    question: str,
    execution_kind: str,
    execution_title: str,
    rows: List[Dict[str, Any]],
    fallback_hint: Optional[str],
    *,
    force: bool = False,
) -> Optional[str]:
    """
    Produce a concise natural-language summary of retrieved rows / aggregates.
    Returns None when API is unavailable or the LLM fails.
    """
    if not force and not _groq_nl_summary_enabled():
        return None
    if not os.getenv("GROQ_API_KEY", "").strip():
        return None

    preview = rows[:30]
    hb = fallback_hint or ""
    user_block = (
        f"USER_QUESTION:\n{question.strip()}\n\n"
        f"EXECUTION_KIND: {execution_kind}\nTITLE: {execution_title}\n\n"
        f"FIRST_ROWS_JSON:\n{preview}\n\n"
        f"GUIDANCE_SNIPPET (may be empty): {hb}\n\n"
        "Write ONE short paragraph (≤ 4 sentences). "
        "State the direct answer implied by the data (figures, extremes, counts). "
        "Do NOT describe internal implementation. "
        "If there are no rows, say so clearly."
    )
    system = (
        "You summarise tabular IMF query results for a staff user. "
        "Be factual; use numbers from the preview. Never invent entities not shown."
    )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore

        llm = _groq_llm(_groq_models_to_try()[0], max_tokens=320)
        out = llm.invoke([SystemMessage(content=system), HumanMessage(content=user_block)])
        text = str(getattr(out, "content", "") or "").strip()
        return text or None
    except Exception as exc:
        logger.warning("Groq NL answer summary failed: %s", exc)
        return None


def generate_nl_summary(
    question: str,
    spec: AnalyticsSpec,
    rows: List[Dict[str, Any]],
) -> str:
    """
    Generate a human-readable summary for an aggregate result.
    Prefers Groq; falls back to a simple count line.
    """
    from app.services import visualization_service as vis

    headline = vis._build_title(spec)
    groq_sum = try_groq_nl_answer_summary(
        question,
        execution_kind="aggregate",
        execution_title=headline,
        rows=rows,
        fallback_hint=None,
    )
    if groq_sum:
        return groq_sum

    n = len(rows)
    if n == 0:
        return f"No matching rows — {headline}"
    return f"{headline} ({n} row{'s' if n != 1 else ''})"
