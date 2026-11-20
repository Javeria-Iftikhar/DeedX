"""
schemas/dashboard.py — Pydantic response models for dynamic dashboard output.

These are the user-facing response shapes returned by the analytics endpoints.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DashboardMetadata(BaseModel):
    """Metadata block appended to every dashboard response."""
    generated_by: str = "analytics_engine"
    planner: Optional[str] = None  # groq | rules — how the query was interpreted
    module: str
    applied_filters: List[Dict[str, Any]] = []
    group_by: List[str] = []
    row_count: int = 0
    timestamp: str = ""

    def __init__(self, **data):
        if not data.get("timestamp"):
            data["timestamp"] = datetime.utcnow().isoformat() + "Z"
        super().__init__(**data)


class DashboardResponse(BaseModel):
    """
    Standard dynamic dashboard JSON shape.

    Example:
        {
          "title": "GDP Trends by Country",
          "chart_type": "line",
          "x_axis": "country_name",
          "y_axis": "avg_GDP",
          "data": [...],
          "summary": "...",
          "metadata": {...}
        }
    """
    title: str
    chart_type: str
    x_axis: Optional[str] = None
    y_axis: Optional[str] = None
    data: List[Dict[str, Any]] = []
    summary: Optional[str] = None
    metadata: DashboardMetadata
    export_format: Optional[str] = None  # "pdf" | "csv" when user asked to export


class AnalyticsQueryHistoryItem(BaseModel):
    """One entry from the analytics query history."""
    log_id: int
    user_id: int
    query: str
    module: str
    success: bool
    timestamp: str


class AnalyticsHistoryResponse(BaseModel):
    items: List[AnalyticsQueryHistoryItem]
    total: int
    page: int
    page_size: int
