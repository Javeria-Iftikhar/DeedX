"""
schemas/visualization.py — Chart and visualization configuration schemas.
"""

from typing import List, Optional
from pydantic import BaseModel


class AxisConfig(BaseModel):
    field: str
    label: str


class LegendConfig(BaseModel):
    field: str
    values: List[str] = []


class VisualizationConfig(BaseModel):
    """
    Computed by visualization_service; tells the frontend exactly how
    to render the data (which fields go on which axis, chart type, etc.).
    """
    chart_type: str
    x_axis: Optional[AxisConfig] = None
    y_axis: Optional[AxisConfig] = None
    legend: Optional[LegendConfig] = None
    title: str = ""
    color_scheme: str = "default"
