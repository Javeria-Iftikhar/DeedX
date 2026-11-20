"""
services/dashboard_export_service.py — PDF/CSV rendering from DashboardResponse.

Used by POST /analytics/export/* (and mirrored /llm/export/* routes). The NL /
LLM pipeline runs first (same as /analytics/query); this module only renders the
structured dashboard payload.
"""

from __future__ import annotations

import csv
import io
import math
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.analytics_schemas.dashboard import DashboardResponse


def safe_filename_stub(title: str, ext: str) -> str:
    base = re.sub(r"[^\w\s\-]", "", title)[:72]
    base = re.sub(r"[\s\-]+", "-", base).strip("-") or "dashboard-export"
    return f"{base}.{ext.lower()}"


def _scalar_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return str(float(v))
    if isinstance(v, float):
        return str(v) if math.isfinite(v) else ""
    if isinstance(v, (dict, list)):
        return str(v)
    return str(v)


def _try_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _union_keys(rows: List[Dict[str, Any]]) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                ordered.append(k)
    return ordered


def dashboard_to_csv_bytes(dashboard: DashboardResponse) -> Tuple[bytes, str]:
    """Return UTF-8 CSV bytes and a suggested filename stub."""
    rows = dashboard.data or []
    if not rows:
        buf = io.StringIO()
        buf.write('"message"\r\n"No rows returned for this query."\r\n')
        return buf.getvalue().encode("utf-8-sig"), safe_filename_stub(dashboard.title, "csv")

    keys = _union_keys(rows)
    sout = io.StringIO()
    writer = csv.DictWriter(sout, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _scalar_str(row.get(k)) for k in keys})
    return sout.getvalue().encode("utf-8-sig"), safe_filename_stub(dashboard.title, "csv")


def _chart_png_bytes(
    chart_type: str,
    x_axis: Optional[str],
    y_axis: Optional[str],
    rows: List[Dict[str, Any]],
    title: str,
) -> Optional[bytes]:
    if chart_type == "table" or not rows:
        return None
    if chart_type == "pie":
        return _pie_png(rows, x_axis, y_axis, title)
    if chart_type not in {"bar", "line", "area"}:
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not x_axis or not y_axis:
        keys = _union_keys(rows)
        numeric_keys = [k for k in keys if any(_try_float(r.get(k)) is not None for r in rows)]
        if len(keys) >= 2:
            x_axis = x_axis or keys[0]
            y_axis = y_axis or (numeric_keys[-1] if numeric_keys else keys[-1])
        elif len(keys) == 1:
            x_axis = x_axis or keys[0]
            y_axis = y_axis or keys[0]

    if not x_axis or not y_axis:
        return None

    labels: List[str] = []
    values: List[float] = []
    for row in rows:
        fv = _try_float(row.get(y_axis))
        if fv is None:
            continue
        labels.append(_scalar_str(row.get(x_axis)) or "?")
        values.append(fv)

    if not values:
        return None
    if chart_type in {"line", "area"} and len(values) < 2:
        return None

    fig, ax = plt.subplots(figsize=(7.2, 3.9), dpi=120)
    try:
        if chart_type == "bar":
            x_pos = range(len(labels))
            ax.bar(x_pos, values, color="#2563eb", edgecolor="#1e40af")
            ax.set_xticks(list(x_pos))
            ax.set_xticklabels(labels, rotation=42, ha="right", fontsize=8)
            ax.set_ylabel(y_axis.replace("_", " "), fontsize=9)
        elif chart_type in {"line", "area"}:
            x_idx = list(range(len(labels)))
            ax.plot(x_idx, values, color="#059669", marker="o", linewidth=2, markersize=4)
            if chart_type == "area":
                ax.fill_between(x_idx, values, alpha=0.22, color="#059669")
            ax.set_xticks(x_idx)
            ax.set_xticklabels(labels, rotation=42, ha="right", fontsize=8)
            ax.set_ylabel(y_axis.replace("_", " "), fontsize=9)
            ax.tick_params(axis="x", pad=4)
            ax.tick_params(axis="y", labelsize=8)
        else:
            plt.close(fig)
            return None

        ax.set_title(title[:120], fontsize=10, pad=12)
        ax.grid(True, linestyle=":", alpha=0.45)
        fig.tight_layout()
        bio = io.BytesIO()
        fig.savefig(bio, format="png", bbox_inches="tight")
        return bio.getvalue()
    finally:
        plt.close(fig)


def _pie_png(
    rows: List[Dict[str, Any]],
    label_key: Optional[str],
    value_key: Optional[str],
    title: str,
) -> Optional[bytes]:
    keys = _union_keys(rows)
    if len(keys) < 2:
        return None
    numeric_keys = [
        k
        for k in keys
        if sum(1 for r in rows if _try_float(r.get(k)) is not None) >= max(1, len(rows) // 2)
    ]
    lk = label_key or keys[0]
    vk = value_key or (numeric_keys[0] if numeric_keys else keys[1])

    if not lk or not vk:
        return None

    labels: List[str] = []
    sizes: List[float] = []
    for row in rows:
        fv = _try_float(row.get(vk))
        if fv is None or fv < 0:
            continue
        labels.append(_scalar_str(row.get(lk)) or "?")
        sizes.append(fv)
    if not sizes:
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.8, 3.9), dpi=120)
    try:
        ax.pie(sizes, labels=labels[:12], autopct="%1.0f%%", textprops={"fontsize": 7})
        ax.set_title(title[:120], fontsize=10, pad=10)
        fig.tight_layout()
        bio = io.BytesIO()
        fig.savefig(bio, format="png", bbox_inches="tight")
        return bio.getvalue()
    finally:
        plt.close(fig)


def _escape_xmlish(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def dashboard_to_pdf_bytes(dashboard: DashboardResponse) -> Tuple[bytes, str]:
    rows = dashboard.data or []
    buf = io.BytesIO()
    page_size = landscape(letter) if rows and len(_union_keys(rows)) > 7 else letter
    doc = SimpleDocTemplate(buf, pagesize=page_size, title=dashboard.title[:100])
    styles = getSampleStyleSheet()
    story: List[Any] = []

    story.append(Paragraph(_escape_xmlish(dashboard.title), styles["Title"]))
    story.append(Spacer(1, 0.15 * inch))
    meta = dashboard.metadata
    generated = getattr(meta, "timestamp", "") or ""
    story.append(
        Paragraph(
            f"<font size=9>{_escape_xmlish(dashboard.summary or '')}<br/><br/>"
            f"<i>Module: {_escape_xmlish(meta.module)} · Rows: {meta.row_count} · "
            f"{_escape_xmlish(generated)}</i></font>",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.2 * inch))

    png = _chart_png_bytes(
        (dashboard.chart_type or "table").lower(),
        dashboard.x_axis,
        dashboard.y_axis,
        rows,
        dashboard.title,
    )
    if png:
        img_bio = io.BytesIO(png)
        w_avail = page_size[0] - doc.leftMargin - doc.rightMargin
        chart_w = min(6.5 * inch, w_avail * 0.95)
        story.append(RLImage(img_bio, width=chart_w, height=chart_w * 0.52))
        story.append(Spacer(1, 0.25 * inch))

    if not rows:
        story.append(Paragraph("<i>No tabular rows in this response.</i>", styles["Normal"]))
        doc.build(story)
        return buf.getvalue(), safe_filename_stub(dashboard.title, "pdf")

    keys = _union_keys(rows)
    head = [_escape_xmlish(k.replace("_", " ")) for k in keys]
    table_data = [head]
    for row in rows:
        table_data.append([_escape_xmlish(_scalar_str(row.get(k)))[:500] for k in keys])

    tbl = Table(table_data, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("WORDWRAP", (0, 0), (-1, -1)),
            ]
        )
    )
    story.append(tbl)

    doc.build(story)
    return buf.getvalue(), safe_filename_stub(dashboard.title, "pdf")
