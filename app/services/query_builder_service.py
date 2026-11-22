"""
services/query_builder_service.py — Translates a validated AnalyticsSpec into
a safe SQLAlchemy ORM query and executes it.

SECURITY GUARANTEES:
  - No raw SQL is constructed or executed.
  - No text() calls.
  - No f-string SQL.
  - Table/column access is mediated entirely through the ORM model attributes
    fetched from analytics_registry — never from user-supplied strings directly.
  - Filter values are passed as ORM bind parameters, never concatenated.

ARCHITECTURE:
  1. Look up the primary model from the registry.
  2. Build SELECT columns (group_by fields + aggregated metrics).
  3. Apply predefined JOINs where join fields are requested.
  4. Apply WHERE filters via ORM filter() with safe value binding.
  5. Apply GROUP BY, ORDER BY, LIMIT/OFFSET.
  6. Execute and return list of dicts.
"""

import decimal
import datetime
import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import func, asc, desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.analytics_registry import ANALYTICS_REGISTRY, get_module
from app.analytics_schemas.analytics import AnalyticsSpec, FilterSpec


# ── Aggregation dispatch ───────────────────────────────────────────────────────

_AGG_FUNCS = {
    "count": func.count,
    "sum":   func.sum,
    "avg":   func.avg,
    "min":   func.min,
    "max":   func.max,
}

# ── Operator dispatch ──────────────────────────────────────────────────────────

def _apply_operator(col, operator: str, value: Any):
    """Return an ORM filter expression for col <op> value."""
    op = (operator or "=").strip().lower()
    if op == "=":
        return col == value
    elif op == "!=":
        return col != value
    elif op == ">":
        return col > value
    elif op == "<":
        return col < value
    elif op == ">=":
        return col >= value
    elif op == "<=":
        return col <= value
    elif op == "in":
        if not isinstance(value, (list, tuple)):
            value = [value]
        return col.in_(value)
    elif op == "ilike":
        return col.ilike(str(value))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported operator: {operator}",
        )


def _get_model_column(model, field: str):
    """
    Safely retrieve a column attribute from an ORM model by field name.
    Raises 400 if the attribute doesn't exist (should never happen after
    field whitelist validation, but defence-in-depth).
    """
    col = getattr(model, field, None)
    if col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field '{field}' does not exist on model '{model.__tablename__}'.",
        )
    return col


# ── Serialisation helper ───────────────────────────────────────────────────────

def _serialise(v: Any) -> Any:
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return str(v)
    return v


# ── Main builder ───────────────────────────────────────────────────────────────

def build_and_execute(db: Session, spec: AnalyticsSpec) -> List[Dict[str, Any]]:
    """
    Build and execute a safe ORM query from the validated AnalyticsSpec.

    Returns a list of row dicts with serialised values.
    """
    registry_entry = get_module(spec.module)
    if not registry_entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown module: {spec.module}",
        )

    primary_model = registry_entry["model"]
    predefined_joins = registry_entry.get("joins", [])

    # ── 1. Determine which joins are needed ────────────────────────────────────
    # A join is needed if any requested field (metric, group_by, filter)
    # matches the join's alias_field.
    all_requested_fields = (
        [m.field for m in spec.metrics]
        + spec.group_by
        + [f.field for f in spec.filters]
        + ([spec.sort.field] if spec.sort else [])
    )

    def _join_is_needed(j: Dict[str, Any]) -> bool:
        req_any = j.get("include_when_any_field")
        if req_any and any(f in all_requested_fields for f in req_any):
            return True
        alias = j.get("alias_field")
        if alias is None:
            # Merge-join rows (e.g. EconomicRecord): needed when any of its columns are used
            jm = j.get("join_model")
            if jm is not None and hasattr(jm, "__table__"):
                if any(f in all_requested_fields for f in jm.__table__.columns.keys()):
                    return True
            return False
        extras = list((j.get("extra_aliases") or {}).keys())
        join_fields = [alias] + extras
        return any(n in all_requested_fields for n in join_fields if n)

    needed_joins: List[Dict[str, Any]] = []
    seen_ids: Set[int] = set()
    for j in predefined_joins:
        if not _join_is_needed(j):
            continue
        jid = id(j)
        if jid not in seen_ids:
            needed_joins.append(j)
            seen_ids.add(jid)

    # Bridge joins (e.g. EconomicRecord via EconomicIndicator) require parent tables in FROM.
    changed = True
    while changed:
        changed = False
        for j in list(needed_joins):
            bridge = j.get("left_join_model")
            if bridge is None:
                continue
            for parent in predefined_joins:
                if parent.get("join_model") is bridge and id(parent) not in seen_ids:
                    needed_joins.append(parent)
                    seen_ids.add(id(parent))
                    changed = True

    def _sort_joins_by_dependency(joins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ordered: List[Dict[str, Any]] = []
        placed: Set[int] = set()

        def visit(j: Dict[str, Any]) -> None:
            jid = id(j)
            if jid in placed:
                return
            bridge = j.get("left_join_model")
            if bridge is not None:
                for parent in joins:
                    if parent.get("join_model") is bridge:
                        visit(parent)
            ordered.append(j)
            placed.add(jid)

        for j in joins:
            visit(j)
        return ordered

    needed_joins = _sort_joins_by_dependency(needed_joins)

    # ── 2. Build a field resolver: field_name → ORM column expression ──────────
    # Start with all columns on primary model
    field_resolver: Dict[str, Any] = {}
    for join in needed_joins:
        if join["alias_field"] and join["source_col"] is not None:
            field_resolver[join["alias_field"]] = join["source_col"]
            for ek, expr in (join.get("extra_aliases") or {}).items():
                field_resolver[ek] = expr
        elif join["alias_field"] is None:
            # Merge join model columns (e.g. EconomicRecord)
            jm = join["join_model"]
            for col_name in jm.__table__.columns.keys():
                if col_name not in field_resolver:
                    field_resolver[col_name] = getattr(jm, col_name)

    # Virtual aliases on the primary module (e.g. country_name → Country.name)
    for alias, expr in (registry_entry.get("virtual_aliases") or {}).items():
        field_resolver[alias] = expr

    # Primary model columns fill in the rest
    for col_name in primary_model.__table__.columns.keys():
        if col_name not in field_resolver:
            field_resolver[col_name] = getattr(primary_model, col_name)

    def resolve(field: str):
        if field in field_resolver:
            return field_resolver[field]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resolve field '{field}' for module '{spec.module}'.",
        )

    # ── 3. Build SELECT clause ─────────────────────────────────────────────────
    select_cols = []
    col_labels: List[str] = []

    for group_field in spec.group_by:
        col = resolve(group_field)
        select_cols.append(col.label(group_field))
        col_labels.append(group_field)

    for metric in spec.metrics:
        col = resolve(metric.field)
        agg_fn = _AGG_FUNCS[metric.aggregation.lower()]
        label = f"{metric.aggregation}_{metric.field}"
        select_cols.append(agg_fn(col).label(label))
        col_labels.append(label)

    # ── 4. Start query (anchor FROM to primary model so joins keep correct roots) ─
    # Without select_from(), SQLAlchemy can pick a joined table as the implicit FROM
    # when aggregates reference it first (e.g. economic), producing invalid SQL that
    # references primary_model in ON clauses but omits it from FROM.
    query = db.query(*select_cols).select_from(primary_model)

    # ── 5. Apply JOINs ─────────────────────────────────────────────────────────
    for j in needed_joins:
        join_model = j["join_model"]
        bridge = j.get("left_join_model")
        left_entity = primary_model if bridge is None else bridge
        left_col = getattr(left_entity, j["left_col"])
        right_col = getattr(join_model, j["right_col"])
        query = query.join(join_model, left_col == right_col, isouter=True)

    # ── 6. Apply WHERE filters ─────────────────────────────────────────────────
    for f in spec.filters:
        col = resolve(f.field)
        expr = _apply_operator(col, f.operator, f.value)
        query = query.filter(expr)

    # ── 7. GROUP BY ────────────────────────────────────────────────────────────
    if spec.group_by:
        group_cols = [resolve(g) for g in spec.group_by]
        query = query.group_by(*group_cols)

    # ── 8. ORDER BY ───────────────────────────────────────────────────────────
    if spec.sort:
        sort_field = spec.sort.field
        metric_by_field = {m.field: m for m in spec.metrics}

        def _metric_order_expr(metric) -> Any:
            col = resolve(metric.field)
            agg_fn = _AGG_FUNCS[metric.aggregation.lower()]
            return agg_fn(col)

        if spec.group_by:
            # With GROUP BY, only grouped columns or aggregated metrics are valid in ORDER BY.
            if sort_field in spec.group_by:
                order_expr = resolve(sort_field)
            elif sort_field in metric_by_field:
                order_expr = _metric_order_expr(metric_by_field[sort_field])
            elif any(f"{m.aggregation}_{m.field}" == sort_field for m in spec.metrics):
                for m in spec.metrics:
                    if f"{m.aggregation}_{m.field}" == sort_field:
                        order_expr = _metric_order_expr(m)
                        break
            elif spec.metrics:
                order_expr = _metric_order_expr(spec.metrics[0])
            else:
                order_expr = resolve(sort_field)
        elif sort_field in metric_by_field:
            order_expr = _metric_order_expr(metric_by_field[sort_field])
        else:
            order_expr = resolve(sort_field)

        if spec.sort.direction.lower() == "desc":
            query = query.order_by(desc(order_expr))
        else:
            query = query.order_by(asc(order_expr))

    # ── 9. LIMIT / OFFSET ─────────────────────────────────────────────────────
    if spec.limit:
        query = query.limit(spec.limit)
    if spec.offset:
        query = query.offset(spec.offset)

    # ── 10. Execute and serialise ──────────────────────────────────────────────
    try:
        rows = query.all()
    except Exception as exc:
        # Log the real error server-side; never leak DB details to client
        logger.error(
            "DB execution error for module=%r spec=%r: %s",
            spec.module, spec, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The query could not be executed against the database. Please try a different query or contact support.",
        )

    result = []
    for row in rows:
        if hasattr(row, "_mapping"):
            row_dict = {k: _serialise(v) for k, v in row._mapping.items()}
        elif hasattr(row, "_fields"):
            row_dict = {k: _serialise(v) for k, v in zip(col_labels, row)}
        else:
            row_dict = {col_labels[0]: _serialise(row)}
        result.append(row_dict)

    return result
