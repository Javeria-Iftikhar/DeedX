"""
report_generation_service.py — Structured economic PDF reports from NL prompts.

Builds a full report (heading, introduction, data table, dashboard-style charts,
conclusion) and returns PDF bytes. Used by POST /reports/generate.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app import models
from app.services.dashboard_export_service import _chart_png_bytes, safe_filename_stub
from app.services.analytics_llm_service import try_groq_nl_answer_summary

# Dashboard / Economic page palette (matches frontend chartTheme + pages)
CHART_COLORS = ["#22D3EE", "#3B82F6", "#1D4ED8", "#7DD3FC", "#0891b2"]
CHART_GRID = "#94A3B8"

_TOPIC_ALIASES: Dict[str, List[str]] = {
    "inflation": ["inflation", "infl"],
    "gdp": ["gdp", "gross domestic"],
    "cpi": ["cpi", "consumer price", "price index"],
    "interest_rate": ["interest", "interest rate", "rates"],
    "exchange_rate": ["exchange", "fx", "forex", "currency rate"],
    "money_supply": ["money supply", "m2", "monetary"],
    "industrial_output": ["industrial", "manufacturing"],
    "agricultural_output": ["agricultural", "agriculture", "farm"],
    "services_output": ["services sector", "services output", "services"],
}

_METRIC_COLUMNS: Dict[str, str] = {
    "inflation": "inflation",
    "gdp": "GDP",
    "cpi": "CPI",
    "interest_rate": "interest_rate",
    "exchange_rate": "exchange_rate",
    "money_supply": "money_supply",
    "industrial_output": "industrial_output",
    "agricultural_output": "agricultural_output",
    "services_output": "services_output",
}

_DEFAULT_TOPICS = ("gdp", "inflation", "cpi")

_REPORT_PROMPT_RE = re.compile(
    r"\b(?:generate|create|write|build|produce|prepare|compile|draft)\s+"
    r"(?:a\s+)?(?:full\s+)?report\b"
    r"|\b(?:generate|create|write|build|prepare|compile|draft)\s+"
    r"(?:a\s+)?report\s+on\b"
    r"|\b(?:full|detailed|comprehensive)\s+(?:economic\s+)?report\s+(?:on|about|for)\b",
    re.IGNORECASE,
)


_ANALYTICS_START_RE = re.compile(
    r"^\s*(?:show|list|display|get|give\s+me|what\s+(?:is|are)|how\s+many|"
    r"top\s+\d+|average|total|compare|chart|plot|graph)\b",
    re.IGNORECASE,
)

_REPORT_ACTION_RE = re.compile(
    r"\b(?:generate|create|write|build|prepare|compile|draft)\s+"
    r"(?:a\s+)?(?:(?:full|detailed|comprehensive)\s+)?report\b",
    re.IGNORECASE,
)


def is_structured_report_prompt(prompt: str) -> bool:
    """
    True only when the *current* message explicitly asks to generate a full PDF report.
    Plain analytics phrasing (show/list/top/average …) never qualifies.
    """
    text = (prompt or "").strip()
    if not text:
        return False
    low = text.lower()
    if not re.search(r"\breport\b", low):
        return False
    if _ANALYTICS_START_RE.match(low) and not _REPORT_ACTION_RE.search(low):
        return False
    return bool(_REPORT_PROMPT_RE.search(low))


@dataclass
class ChartSpec:
    chart_type: str
    x_axis: str
    y_axes: List[str]
    title: str


@dataclass
class ReportDocument:
    title: str
    intro: str
    conclusion: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    charts: List[ChartSpec] = field(default_factory=list)
    generated_at: str = ""


def parse_report_topics(prompt: str) -> List[str]:
    """Infer economic metrics from a natural-language prompt."""
    text = prompt.lower()
    found: List[str] = []
    for topic, aliases in _TOPIC_ALIASES.items():
        if any(a in text for a in aliases):
            found.append(topic)
    if not found:
        found = list(_DEFAULT_TOPICS)
    # Preserve stable order
    order = list(_METRIC_COLUMNS.keys())
    return [t for t in order if t in found]


def _title_from_topics(topics: Sequence[str], prompt: str) -> str:
    labels = {
        "inflation": "Inflation",
        "gdp": "GDP",
        "cpi": "CPI",
        "interest_rate": "Interest Rates",
        "exchange_rate": "Exchange Rates",
        "money_supply": "Money Supply",
        "industrial_output": "Industrial Output",
        "agricultural_output": "Agricultural Output",
        "services_output": "Services Output",
    }
    parts = [labels.get(t, t.replace("_", " ").title()) for t in topics[:4]]
    if len(topics) > 4:
        parts.append("…")
    joined = " & ".join(parts) if parts else "Economic Indicators"
    stub = re.sub(r"\s+", " ", prompt.strip())[:60]
    if stub and len(stub) > 8:
        return f"Economic Report: {joined}"
    return f"IMF Economic Report — {joined}"


def _float_val(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_economic_report_rows(
    db: Session,
    topics: Sequence[str],
    limit: int = 36,
) -> List[Dict[str, Any]]:
    """Join indicators, derived records, and countries for report tables/charts."""
    q = (
        db.query(
            models.Country.name.label("country"),
            models.EconomicIndicator.record_date,
            models.EconomicIndicator.CPI,
            models.EconomicIndicator.interest_rate,
            models.EconomicIndicator.exchange_rate,
            models.EconomicIndicator.money_supply,
            models.EconomicIndicator.industrial_output,
            models.EconomicIndicator.agricultural_output,
            models.EconomicIndicator.services_output,
            models.EconomicRecord.GDP,
            models.EconomicRecord.inflation,
        )
        .join(
            models.EconomicIndicator,
            models.EconomicIndicator.country_id == models.Country.country_id,
        )
        .join(
            models.EconomicRecord,
            models.EconomicRecord.indicator_id == models.EconomicIndicator.indicator_id,
            isouter=True,
        )
        .order_by(models.EconomicIndicator.record_date.desc())
        .limit(limit)
    )
    rows: List[Dict[str, Any]] = []
    for r in q.all():
        row: Dict[str, Any] = {
            "country": r.country or "Unknown",
            "record_date": str(r.record_date) if r.record_date else "",
            "CPI": _float_val(r.CPI),
            "interest_rate": _float_val(r.interest_rate),
            "exchange_rate": _float_val(r.exchange_rate),
            "money_supply": _float_val(r.money_supply),
            "industrial_output": _float_val(r.industrial_output),
            "agricultural_output": _float_val(r.agricultural_output),
            "services_output": _float_val(r.services_output),
            "GDP": _float_val(r.GDP),
            "inflation": _float_val(r.inflation),
        }
        rows.append(row)
    return rows


def _table_columns(topics: Sequence[str]) -> List[str]:
    base = ["country", "record_date"]
    for t in topics:
        col = _METRIC_COLUMNS.get(t)
        if col and col not in base:
            base.append(col)
    return base


def build_chart_specs(rows: List[Dict[str, Any]], topics: Sequence[str]) -> List[ChartSpec]:
    """Charts aligned with dashboard / economic pages: line trends + bar comparisons."""
    if not rows:
        return []

    charts: List[ChartSpec] = []
    metric_cols = [_METRIC_COLUMNS[t] for t in topics if t in _METRIC_COLUMNS]

    # Line: CPI + interest (EconomicPage pattern) when relevant
    line_metrics: List[str] = []
    if "cpi" in topics or "CPI" in metric_cols:
        line_metrics.append("CPI")
    if "interest_rate" in topics:
        line_metrics.append("interest_rate")
    if not line_metrics and "inflation" in topics:
        line_metrics.append("inflation")
    if line_metrics:
        charts.append(
            ChartSpec(
                chart_type="line",
                x_axis="record_date",
                y_axes=line_metrics[:2],
                title="Macroeconomic Trend",
            )
        )

    # Bar: primary numeric metric by country (Dashboard bar style)
    bar_metric = None
    for pref in ("GDP", "inflation", "CPI", "exchange_rate"):
        if pref in metric_cols:
            bar_metric = pref
            break
    if bar_metric:
        charts.append(
            ChartSpec(
                chart_type="bar",
                x_axis="country",
                y_axes=[bar_metric],
                title=f"{bar_metric.replace('_', ' ')} by Country",
            )
        )

    # Area: second metric over time when GDP/inflation requested
    if "gdp" in topics or "inflation" in topics:
        area_y = "GDP" if "gdp" in topics else "inflation"
        if area_y not in line_metrics:
            charts.append(
                ChartSpec(
                    chart_type="area",
                    x_axis="record_date",
                    y_axes=[area_y],
                    title=f"{area_y} Over Time",
                )
            )

    return charts[:3]


def _fallback_intro(title: str, rows: List[Dict[str, Any]], topics: Sequence[str]) -> str:
    n = len(rows)
    countries = len({r.get("country") for r in rows if r.get("country")})
    topic_txt = ", ".join(t.replace("_", " ") for t in topics)
    if n == 0:
        return (
            f"This report addresses {topic_txt} based on your request. "
            "No economic indicator rows are currently stored in the system; "
            "add indicators under Economic Data to populate future reports."
        )
    return (
        f"This report presents an analysis of {topic_txt} across IMF member countries. "
        f"The dataset includes {n} indicator observation(s) spanning {countries} country/countries. "
        f"Figures below summarize recent macroeconomic movements supporting policy review."
    )


def _fallback_conclusion(rows: List[Dict[str, Any]], topics: Sequence[str]) -> str:
    if not rows:
        return (
            "Conclusion: Insufficient stored data to draw quantitative conclusions. "
            "Seed economic indicators and re-run report generation when data is available."
        )
    # Simple extrema from first numeric topic column
    col = _METRIC_COLUMNS.get(topics[0], "GDP") if topics else "GDP"
    vals = [(r.get("country"), _float_val(r.get(col))) for r in rows]
    vals = [(c, v) for c, v in vals if v is not None]
    if not vals:
        return (
            "Conclusion: Observed series show mixed movements across member countries. "
            "Continue monitoring through the Economic Indicators dashboard for updates."
        )
    top = max(vals, key=lambda x: x[1])
    low = min(vals, key=lambda x: x[1])
    return (
        f"Conclusion: {col.replace('_', ' ')} ranges from {low[1]:,.2f} ({low[0]}) "
        f"to {top[1]:,.2f} ({top[0]}) in the sampled period. "
        "Stakeholders should align lending and surveillance priorities with these trends "
        "and refresh this report as new indicator releases are recorded."
    )


def _generate_section(
    prompt: str,
    rows: List[Dict[str, Any]],
    title: str,
    section: str,
    fallback: str,
) -> str:
    instruction = (
        f"Write a professional {section} (2–4 sentences) for an IMF economic PDF report titled '{title}'. "
        f"User request: {prompt.strip()}. "
        "Use only numbers present in the data preview. Be concise and policy-oriented."
    )
    text = try_groq_nl_answer_summary(
        instruction,
        execution_kind="report",
        execution_title=title,
        rows=rows[:25],
        fallback_hint=fallback,
        force=True,
    )
    return text.strip() if text else fallback


def build_report_document(db: Session, prompt: str) -> ReportDocument:
    topics = parse_report_topics(prompt)
    rows = fetch_economic_report_rows(db, topics)
    title = _title_from_topics(topics, prompt)
    columns = _table_columns(topics)
    table_rows = [{k: r.get(k) for k in columns} for r in rows]
    charts = build_chart_specs(rows, topics)

    intro_fb = _fallback_intro(title, rows, topics)
    concl_fb = _fallback_conclusion(rows, topics)
    intro = _generate_section(prompt, rows, title, "introduction", intro_fb)
    conclusion = _generate_section(prompt, rows, title, "conclusion", concl_fb)

    return ReportDocument(
        title=title,
        intro=intro,
        conclusion=conclusion,
        columns=columns,
        rows=table_rows,
        charts=charts,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


def _multi_series_chart_png(
    chart_type: str,
    rows: List[Dict[str, Any]],
    x_axis: str,
    y_axes: List[str],
    title: str,
) -> Optional[bytes]:
    """Dashboard-style charts with cyan/blue palette (Economic + Operations pages)."""
    if not rows or not y_axes:
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Build ordered x labels (preserve first-seen order)
    x_labels: List[str] = []
    seen_x: set = set()
    for row in rows:
        xl = str(row.get(x_axis) or "?")
        if xl not in seen_x:
            seen_x.add(xl)
            x_labels.append(xl)

    if not x_labels:
        return None

    fig, ax = plt.subplots(figsize=(7.4, 4.0), dpi=120)
    fig.patch.set_facecolor("#0a0f1a")
    ax.set_facecolor("#0f172a")
    ax.tick_params(colors=CHART_GRID, labelsize=8)
    ax.title.set_color("#EAF6FF")
    for spine in ax.spines.values():
        spine.set_color("#475569")

    x_idx = {lbl: i for i, lbl in enumerate(x_labels)}
    ct = chart_type.lower()

    for i, y_key in enumerate(y_axes):
        color = CHART_COLORS[i % len(CHART_COLORS)]
        series: List[Optional[float]] = [None] * len(x_labels)
        for row in rows:
            xl = str(row.get(x_axis) or "?")
            if xl not in x_idx:
                continue
            series[x_idx[xl]] = _float_val(row.get(y_key))

        ys = [v if v is not None else 0.0 for v in series]
        if ct == "bar":
            width = 0.8 / max(len(y_axes), 1)
            offset = (i - (len(y_axes) - 1) / 2) * width
            positions = [xi + offset for xi in range(len(x_labels))]
            ax.bar(positions, ys, width=width * 0.9, label=y_key.replace("_", " "), color=color, edgecolor="#0f172a")
            if i == 0:
                ax.set_xticks(range(len(x_labels)))
                ax.set_xticklabels(x_labels, rotation=38, ha="right", fontsize=7, color=CHART_GRID)
        elif ct in {"line", "area"}:
            ax.plot(range(len(x_labels)), ys, color=color, marker="o", linewidth=2, markersize=3, label=y_key.replace("_", " "))
            if ct == "area":
                ax.fill_between(range(len(x_labels)), ys, alpha=0.22, color=color)
            if i == 0:
                ax.set_xticks(range(len(x_labels)))
                ax.set_xticklabels(x_labels, rotation=38, ha="right", fontsize=7, color=CHART_GRID)
        else:
            plt.close(fig)
            return _chart_png_bytes(ct, x_axis, y_axes[0], rows, title)

    ax.set_title(title[:100], fontsize=10, color="#EAF6FF", pad=10)
    ax.grid(True, linestyle=":", alpha=0.35, color=CHART_GRID)
    if len(y_axes) > 1 or ct == "bar":
        leg = ax.legend(fontsize=7, facecolor="#1e293b", edgecolor="#334155", labelcolor="#EAF6FF")
        if leg:
            leg.get_frame().set_alpha(0.92)
    fig.tight_layout()
    bio = io.BytesIO()
    fig.savefig(bio, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return bio.getvalue()


def report_document_to_pdf_bytes(doc: ReportDocument) -> Tuple[bytes, str]:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=letter, title=doc.title[:100])
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=8,
    )
    story: List[Any] = []

    story.append(Paragraph(esc(doc.title), styles["Title"]))
    story.append(Spacer(1, 0.12 * inch))
    story.append(Paragraph(f"<i>Generated {esc(doc.generated_at)}</i>", styles["Normal"]))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("<b>Introduction</b>", styles["Heading2"]))
    story.append(Paragraph(esc(doc.intro), body))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("<b>Supporting Data</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))

    if doc.rows:
        head = [esc(c.replace("_", " ").title()) for c in doc.columns]
        table_data = [head]
        for row in doc.rows:
            table_data.append(
                [
                    esc(str(row.get(c) if row.get(c) is not None else ""))[:120]
                    for c in doc.columns
                ]
            )
        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(tbl)
    else:
        story.append(Paragraph("<i>No economic data rows available.</i>", body))

    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph("<b>Charts</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.1 * inch))

    full_rows = doc.rows
    for chart in doc.charts:
        png = _multi_series_chart_png(
            chart.chart_type,
            full_rows,
            chart.x_axis,
            chart.y_axes,
            chart.title,
        )
        if not png and len(chart.y_axes) == 1:
            png = _chart_png_bytes(
                chart.chart_type,
                chart.x_axis,
                chart.y_axes[0],
                full_rows,
                chart.title,
            )
        if png:
            img_bio = io.BytesIO(png)
            w = 6.2 * inch
            story.append(Paragraph(f"<i>{esc(chart.title)}</i>", body))
            story.append(RLImage(img_bio, width=w, height=w * 0.52))
            story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("<b>Conclusion</b>", styles["Heading2"]))
    story.append(Paragraph(esc(doc.conclusion), body))

    pdf.build(story)
    fname = safe_filename_stub(doc.title, "pdf")
    return buf.getvalue(), fname


def generate_report_pdf(db: Session, prompt: str) -> Tuple[bytes, str]:
    """Main entry: prompt → structured report → PDF bytes + filename."""
    doc = build_report_document(db, prompt.strip())
    return report_document_to_pdf_bytes(doc)


def build_report_dashboard_response(db: Session, prompt: str):
    """
    Dashboard JSON for Fiscal Analytics chat when user asks for a full report.
    Includes intro, table, chart axes, conclusion, and export_format=pdf.
    """
    from app.analytics_schemas.dashboard import DashboardMetadata, DashboardResponse

    doc = build_report_document(db, prompt.strip())
    chart_type = "table"
    x_axis: Optional[str] = None
    y_axis: Optional[str] = None
    if doc.charts:
        primary = doc.charts[0]
        chart_type = primary.chart_type
        x_axis = primary.x_axis
        y_axis = primary.y_axes[0] if primary.y_axes else None

    summary = (
        f"Introduction\n{doc.intro}\n\n"
        f"Conclusion\n{doc.conclusion}\n\n"
        "Your full PDF report (heading, supporting table, and charts) is downloading now."
    )

    meta = DashboardMetadata(
        module="report:economic",
        row_count=len(doc.rows),
        applied_filters=[{"topics": parse_report_topics(prompt)}],
    )

    return DashboardResponse(
        title=doc.title,
        chart_type=chart_type,
        x_axis=x_axis,
        y_axis=y_axis,
        data=doc.rows,
        summary=summary,
        metadata=meta,
        export_format="pdf",
    )
