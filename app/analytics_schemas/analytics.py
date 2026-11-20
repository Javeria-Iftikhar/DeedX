"""
schemas/analytics.py — Pydantic models for the analytics pipeline.

These are the internal data contracts between:
  query_parser_service → analytics_permissions → query_builder_service → visualization_service

None of these are ever returned directly to the user (they are internal).
The DashboardResponse in schemas/dashboard.py is what the user receives.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, field_validator, model_validator


# ── Inbound request from user ─────────────────────────────────────────────────

class NaturalLanguageQueryRequest(BaseModel):
    """User-facing: a free-text natural language question."""
    query: str

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty.")
        if len(v) > 1000:
            raise ValueError("Query too long (max 1000 characters).")
        return v


# ── Internal analytics specification (output of parser, input to builder) ─────

class MetricSpec(BaseModel):
    """A single aggregated metric: e.g. avg(inflation)."""
    field: str
    aggregation: str   # count | sum | avg | min | max


class FilterSpec(BaseModel):
    """A single WHERE-clause condition."""
    field: str
    operator: str      # = != > < >= <= in
    value: Any


class SortSpec(BaseModel):
    """ORDER BY specification."""
    field: str
    direction: str = "desc"   # asc | desc


class AnalyticsSpec(BaseModel):
    """
    Fully structured analytics specification produced by the parser.

    This is the internal representation that flows through the permission
    checker and query builder. It is NEVER serialised back to the user.
    """
    module: str                          # e.g. "loan", "economic"
    metrics: List[MetricSpec]
    group_by: List[str] = []
    filters: List[FilterSpec] = []
    chart_type: Optional[str] = "bar"
    sort: Optional[SortSpec] = None
    limit: Optional[int] = 10
    offset: int = 0

    @model_validator(mode="after")
    def at_least_one_metric(self) -> "AnalyticsSpec":
        if not self.metrics:
            raise ValueError("At least one metric is required.")
        return self
