"""
routers/reports.py — Natural-language economic report generation (PDF).

POST /reports/generate — prompt such as "generate report on inflation and GDP"
returns a structured PDF with heading, introduction, data table, charts, and conclusion.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db, require_analyst
from app import models
from app.audit import write_audit_log
from app.services.report_generation_service import generate_report_pdf

router = APIRouter(prefix="/reports", tags=["Report Generation"])
logger = logging.getLogger(__name__)


class ReportGenerateRequest(BaseModel):
    """Natural-language report request."""

    prompt: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description='e.g. "generate report on inflation and GDP"',
        examples=["generate report on inflation and GDP"],
    )


@router.post(
    "/generate",
    summary="Generate economic PDF report from prompt",
    description=(
        "Submit a natural-language prompt (e.g. *generate report on inflation/gdp*). "
        "Returns a PDF with a title, introduction, supporting data table, "
        "dashboard-style charts, and conclusion."
    ),
    responses={
        400: {"description": "Invalid or empty prompt"},
        403: {"description": "Analyst or admin role required"},
        500: {"description": "Report could not be built"},
    },
)
def generate_report(
    body: ReportGenerateRequest,
    current_user: models.User = Depends(require_analyst),
    db: Session = Depends(get_db),
) -> Response:
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    try:
        pdf_bytes, filename = generate_report_pdf(db, prompt)
        write_audit_log(
            db,
            current_user.user_id,
            f"Report generated: {prompt[:120]}",
            "Report",
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "generate_report failed user_id=%s prompt=%r: %s",
            current_user.user_id,
            prompt,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate report PDF. Please try again.",
        ) from exc
